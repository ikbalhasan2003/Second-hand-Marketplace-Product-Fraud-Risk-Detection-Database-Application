"""Train RF/LR and evaluate a transparent rules baseline on identical frozen splits."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import platform
import subprocess
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.contract import FEATURE_NAMES, SCHEMA_SHA256, SCHEMA_VERSION
from ml.datasets.io import canonical_json, checksum, load_dataset
from ml.evaluation.metrics import sliced_metrics
from ml.training.preprocessing import FeatureImputer, matrix


def dependency_manifest():
    return {
        "python": ".".join(platform.python_version_tuple()[:2]),
        **{name: importlib.metadata.version(name) for name in ("scikit-learn", "numpy", "scipy", "joblib")},
    }


def code_revision():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return "unversioned"


def training_source_sha256():
    digest = hashlib.sha256()
    package = Path(__file__).resolve().parents[1]
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(b"\x00")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def rules_probabilities(records):
    """Fixed prototype score, unrelated to labels and never tuned against final test."""
    scores = []
    for row in records:
        f = row["features"]
        score = 0.06
        score += 0.20 if f["price_ratio"] is not None and f["price_ratio"] < 0.55 else 0
        score += 0.16 * min(f["keyword_count"], 3)
        score += 0.10 if f["seller_age_days"] < 30 else 0
        score += 0.18 if f["prior_confirmed_fraud_count"] > 0 else 0
        score += 0.10 if f["duplicate_text_count_30d"] >= 3 else 0
        score += 0.05 if f["image_count"] == 0 else 0
        scores.append(min(score, 0.99))
    return np.asarray(scores)


def train(dataset: Path, output: Path, model_version: str) -> dict:
    records, manifest = load_dataset(dataset)
    train_rows = [r for r in records if r["partition"] == "train"]
    labels = np.asarray([int(r["label"] == "fraud") for r in train_rows])
    if len(set(labels)) != 2:
        raise ValueError("Training partition must contain both classes")
    for partition in ("validation", "test"):
        if not any(r["partition"] == partition for r in records):
            raise ValueError(f"Empty {partition} partition; too few independent groups")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    seed = manifest["seed"]
    models = {
        "random_forest": Pipeline([
            ("impute", FeatureImputer()),
            ("classifier", RandomForestClassifier(n_estimators=200, min_samples_leaf=4, class_weight="balanced", random_state=seed, n_jobs=1)),
        ]),
        "logistic_regression": Pipeline([
            ("impute", FeatureImputer()), ("scale", StandardScaler()),
            ("classifier", LogisticRegression(class_weight="balanced", random_state=seed, max_iter=2000)),
        ]),
    }
    for pipeline in models.values():
        pipeline.fit(matrix(train_rows), labels)
    report = {
        "dataset_version": manifest["dataset_version"], "dataset_sha256": manifest["dataset_sha256"],
        "feature_schema": SCHEMA_VERSION, "seed": seed, "synthetic_only": manifest["synthetic_only"],
        "limitations": manifest["limitations"],
        "protocol": "Frozen grouped partitions; imputation/scaling/class weights fit on train only; fixed 0.5 threshold; final test evaluated once, no tuning",
        "rules_definition": "min(.99, .06+.20*[price_ratio<.55]+.16*min(keyword_count,3)+.10*[age<30]+.18*[prior_fraud>0]+.10*[duplicates>=3]+.05*[images=0])",
        "models": {},
    }
    for name in ("rules_baseline", *models):
        report["models"][name] = {}
        for partition in ("train", "validation", "test", "challenge"):
            rows = [r for r in records if r["partition"] == partition]
            if not rows:
                continue
            if name == "rules_baseline":
                probabilities = rules_probabilities(rows)
            else:
                classes = list(models[name].classes_)
                probabilities = models[name].predict_proba(matrix(rows))[:, classes.index(1)]
            report["models"][name][partition] = sliced_metrics(rows, probabilities)
    artifact = output / "pipeline.joblib"
    joblib.dump(models["random_forest"], artifact, compress=3)
    # LR is persisted for reproducibility, but not registered as the active algorithm.
    joblib.dump(models["logistic_regression"], output / "logistic_regression.joblib", compress=3)
    (output / "evaluation.json").write_text(canonical_json(report) + "\n", encoding="utf-8")
    metadata = {
        "version": model_version, "algorithm": "random_forest", "artifact_key": "pipeline.joblib",
        "artifact_sha256": checksum(artifact), "feature_schema": SCHEMA_VERSION,
        "feature_schema_sha256": SCHEMA_SHA256,
        "predictor_order": list(FEATURE_NAMES), "class_mapping": {"fraud": 1, "legitimate": 0},
        "dependency_manifest": dependency_manifest(), "code_revision": code_revision(),
        "training_source_sha256": training_source_sha256(),
        "seed": seed, "dataset_version": manifest["dataset_version"],
        "dataset_sha256": manifest["dataset_sha256"], "evaluation_sha256": checksum(output / "evaluation.json"),
        "synthetic_only": manifest["synthetic_only"], "limitations": manifest["limitations"],
        "imputation_statistics": models["random_forest"].named_steps["impute"].statistics_.tolist(),
        "activation": "Requires trusted operator registration and explicit audited administrator activation",
    }
    (output / "model.json").write_text(canonical_json(metadata) + "\n", encoding="utf-8")
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-version", required=True)
    args = parser.parse_args(argv)
    metadata = train(args.dataset, args.output, args.model_version)
    print(f"Trained {metadata['version']}; SHA256={metadata['artifact_sha256']}; synthetic_only={metadata['synthetic_only']}")


if __name__ == "__main__":
    main()
