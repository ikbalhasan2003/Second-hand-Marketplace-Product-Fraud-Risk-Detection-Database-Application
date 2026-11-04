import copy
import json

import numpy as np
import pytest

from ml.contract import FEATURE_NAMES, keyword_count, normalize_text, validate_record
from ml.datasets.generate import generate_records
from ml.datasets.io import load_dataset, validate_partitions, write_dataset
from ml.datasets.split import assign_partitions
from ml.training.artifacts import load_trusted_pipeline
from ml.training.preprocessing import FeatureImputer, matrix
from ml.training.train import train


def metadata():
    return {
        "dataset_version": "test-synthetic", "generator_version": "scenario-v1", "seed": 42,
        "export_cutoff": "2026-12-31T00:00:00+00:00", "limitations": ["Synthetic-only unit fixture"],
        "sources": [{"source_type": "synthetic", "attribution": "Project generated", "license_access_notes": "Test data"}],
    }


def test_unicode_phrase_boundaries_and_distinct_count():
    assert normalize_text("ＷＩＲＥ—Transfer! Straße") == "wire transfer strasse"
    assert keyword_count("Gift card gift card", "No inspection; gift cardboard") == 2
    assert keyword_count("gift cardboard", "wire transfers") == 0


def test_future_evidence_and_missing_flags_are_rejected():
    record = generate_records(60, 42)[0]
    validate_record(record, metadata()["export_cutoff"])
    invalid = copy.deepcopy(record)
    invalid["feature_evidence"]["latest_source_at"] = invalid["feature_as_of"]
    with pytest.raises(ValueError, match="Future evidence"):
        validate_record(invalid, metadata()["export_cutoff"])
    invalid = copy.deepcopy(record)
    invalid["features"]["price_baseline_missing"] = 1 - invalid["features"]["price_baseline_missing"]
    with pytest.raises(ValueError, match="flag"):
        validate_record(invalid, metadata()["export_cutoff"])


def test_connected_groups_and_challenge_overlap():
    records = generate_records(120, 42)
    records[0]["template_family_key"] = records[100]["template_family_key"]
    assign_partitions(records, 42)
    validate_partitions(records)
    assert records[0]["partition"] == records[100]["partition"]
    records[0]["partition"] = "challenge"
    with pytest.raises(ValueError, match="leakage"):
        validate_partitions(records)


def test_generation_is_reproducible_and_write_once(tmp_path):
    records = generate_records(120, 42)
    assert records == generate_records(120, 42)
    first = write_dataset(tmp_path / "a", records, metadata())
    second = write_dataset(tmp_path / "b", records, metadata())
    assert first == second
    assert load_dataset(tmp_path / "a")[0] == records
    with pytest.raises(FileExistsError):
        write_dataset(tmp_path / "a", records, metadata())
    with (tmp_path / "a" / "records.jsonl").open("a") as output:
        output.write("{}\n")
    with pytest.raises(ValueError, match="checksum"):
        load_dataset(tmp_path / "a")


def test_imputer_fits_only_training_and_handles_all_missing():
    values = np.ones((3, len(FEATURE_NAMES)))
    values[:, 0] = [1, 3, np.nan]
    values[:, 8] = np.nan
    imputer = FeatureImputer().fit(values)
    query = values[:1].copy()
    query[0, 0] = np.nan
    assert imputer.transform(query)[0, 0] == 2
    assert imputer.transform(query)[0, 8] == 0
    assert imputer.statistics_[0] == 2


def test_training_identical_partitions_and_trusted_loading(tmp_path):
    records = generate_records(500, 42)
    write_dataset(tmp_path / "dataset", records, metadata())
    model = train(tmp_path / "dataset", tmp_path / "model", "unit-rf")
    loaded = load_trusted_pipeline(
        tmp_path / "model", model["artifact_key"], model["artifact_sha256"],
        model["feature_schema"], model["dependency_manifest"], model["class_mapping"],
    )
    assert loaded.predict_proba(matrix(records[:2])).shape == (2, 2)
    report = json.loads((tmp_path / "model" / "evaluation.json").read_text())
    assert report["synthetic_only"]
    expected_test = sum(r["partition"] == "test" for r in records)
    for name in report["models"]:
        result = report["models"][name]["test"]["all"]
        assert result["sample_count"] == expected_test
        assert sum(result["confusion_matrix"].values()) == expected_test
    with pytest.raises(ValueError, match="checksum"):
        load_trusted_pipeline(tmp_path / "model", "pipeline.joblib", "0" * 64, model["feature_schema"], model["dependency_manifest"], model["class_mapping"])
    bad = {**model["dependency_manifest"], "joblib": "0.0"}
    with pytest.raises(ValueError, match="dependencies"):
        load_trusted_pipeline(tmp_path / "model", "pipeline.joblib", model["artifact_sha256"], model["feature_schema"], bad, model["class_mapping"])
    with pytest.raises(ValueError, match="escapes"):
        load_trusted_pipeline(tmp_path / "model", "../dataset/manifest.json", "0" * 64, model["feature_schema"], model["dependency_manifest"], model["class_mapping"])
