"""Verify trusted registration metadata before loading executable joblib bytes."""

from __future__ import annotations

from pathlib import Path

import joblib
from sklearn.pipeline import Pipeline

from ml.contract import FEATURE_NAMES, SCHEMA_VERSION
from ml.datasets.io import checksum
from ml.training.train import dependency_manifest


def load_trusted_pipeline(
    root: Path, artifact_key: str, expected_sha256: str, feature_schema: str,
    dependencies: dict, class_mapping: dict,
):
    """All expected values must come from immutable, operator-approved registration.

    A checksum proves identity, not safety: never register uploaded or unknown joblib files.
    """
    root = Path(root).resolve(strict=True)
    relative = Path(artifact_key)
    if relative.is_absolute():
        raise ValueError("Artifact key must be relative to the trusted root")
    artifact = (root / relative).resolve(strict=True)
    if not artifact.is_relative_to(root) or not artifact.is_file():
        raise ValueError("Artifact escapes the trusted root")
    if feature_schema != SCHEMA_VERSION or class_mapping != {"fraud": 1, "legitimate": 0}:
        raise ValueError("Incompatible feature schema or class mapping")
    if dependencies != dependency_manifest():
        raise ValueError("Training and inference dependencies differ")
    if checksum(artifact) != expected_sha256:
        raise ValueError("Artifact checksum mismatch")
    pipeline = joblib.load(artifact)
    if not isinstance(pipeline, Pipeline) or list(pipeline.classes_) != [0, 1]:
        raise ValueError("Unexpected trained pipeline/class order")
    if pipeline.n_features_in_ != len(FEATURE_NAMES):
        raise ValueError("Unexpected trained predictor width")
    return pipeline
