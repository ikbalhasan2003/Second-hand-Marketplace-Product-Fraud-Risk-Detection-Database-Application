"""Shared, immutable marketplace-v1 predictor contract. No identifiers are predictors."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from datetime import datetime

SCHEMA_VERSION = "marketplace-v1"
GENERATOR_VERSION = "scenario-v1"
FEATURE_NAMES = (
    "price_ratio", "comparable_count", "price_baseline_missing", "keyword_count",
    "seller_age_days", "prior_confirmed_fraud_count", "posting_frequency_7d",
    "image_count", "location_difference", "location_missing", "duplicate_text_count_30d",
)
NULLABLE_FEATURES = {"price_ratio", "location_difference"}
KEYWORDS = (
    "wire transfer", "western union", "gift card", "crypto only", "deposit first",
    "pay before viewing", "no inspection", "urgent payment",
)
SCHEMA_DEFINITION = {
    "version": SCHEMA_VERSION, "predictor_order": list(FEATURE_NAMES),
    "nullable": sorted(NULLABLE_FEATURES), "keywords": list(KEYWORDS),
    "normalization": "NFKC/casefold/Unicode-alphanumeric-tokens/space-collapse; title + space + description",
    "time_boundary": "strictly before as_of; lower-inclusive rolling windows; repeatable-read snapshot",
    "price": "latest eligible revision per other product first published in 90d; category/condition/currency equal; median; minimum15",
    "postings": "distinct first publications in7d; include target iff before cutoff; no edits",
    "duplicates": "other same-seller products first published in30d; latest eligible revision; normalized-text SHA256",
    "fraud_history": "distinct other products; latest canonical decision per revision before cutoff; evidence-backed fraud only",
    "seller_age": "nonnegative elapsed seconds /86400",
    "location": "normalized complete-location equality; observed seller profile frozen in snapshot; missing iff either empty",
    "imputation": "train-only median; all-null price=1.0,location=0.0; preserve missing flags",
    "class_mapping": {"fraud": 1, "legitimate": 0},
}
SCHEMA_SHA256 = hashlib.sha256(json.dumps(SCHEMA_DEFINITION, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in value).split())


def text_fingerprint(title: str, description: str) -> str:
    return hashlib.sha256(normalize_text(f"{title} {description}").encode()).hexdigest()


def keyword_count(title: str, description: str) -> int:
    text = f" {normalize_text(f'{title} {description}')} "
    return sum(f" {phrase} " in text for phrase in KEYWORDS)


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamps must have an explicit timezone")
    return result


def validate_features(features: dict) -> None:
    if set(features) != set(FEATURE_NAMES):
        raise ValueError("Features must match the marketplace-v1 predictor set exactly")
    for name in FEATURE_NAMES:
        value = features[name]
        if value is None:
            if name not in NULLABLE_FEATURES:
                raise ValueError(f"Missing required feature: {name}")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Non-numeric feature: {name}")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid feature value: {name}")
        if name not in {"price_ratio", "seller_age_days"} and int(value) != value:
            raise ValueError(f"Expected integer feature: {name}")
    for name in ("price_baseline_missing", "location_missing", "location_difference"):
        if features[name] not in (0, 1, None):
            raise ValueError(f"Invalid binary feature: {name}")
    if features["image_count"] > 6 or features["keyword_count"] > len(KEYWORDS):
        raise ValueError("Feature exceeds the versioned bound")
    if bool(features["price_baseline_missing"]) != (features["price_ratio"] is None):
        raise ValueError("Price missing flag does not match value")
    if (features["price_ratio"] is None) != (features["comparable_count"] < 15):
        raise ValueError("Price ratio requires at least fifteen comparables")
    if bool(features["location_missing"]) != (features["location_difference"] is None):
        raise ValueError("Location missing flag does not match value")


def validate_record(record: dict, cutoff: str) -> None:
    required = {
        "record_key", "seller_group_key", "template_family_key", "duplicate_group_key",
        "feature_schema", "feature_as_of", "features", "feature_evidence", "label",
        "label_source", "label_decided_at", "source_type", "is_synthetic",
        "scenario_version", "category", "partition",
    }
    if set(record) != required:
        raise ValueError("Unexpected or missing record fields; private data is not exported")
    if record["feature_schema"] != SCHEMA_VERSION:
        raise ValueError("Incompatible feature schema")
    validate_features(record["features"])
    as_of = timestamp(record["feature_as_of"])
    if not as_of <= timestamp(record["label_decided_at"]) <= timestamp(cutoff):
        raise ValueError("Label/cutoff chronology is invalid")
    evidence = record["feature_evidence"]
    if set(evidence) != {"latest_source_at", "point_in_time_snapshot"}:
        raise ValueError("Evidence must contain only safe chronology metadata")
    if not evidence["point_in_time_snapshot"]:
        raise ValueError("Historical features require a frozen point-in-time snapshot")
    if timestamp(evidence["latest_source_at"]) >= as_of:
        raise ValueError("Future evidence cannot be used as a predictor")
    if record["label"] not in {"fraud", "legitimate"} or not record["label_source"]:
        raise ValueError("A traceable resolved label is required")
    if record["source_type"] not in {"synthetic", "project_review", "external"}:
        raise ValueError("Unknown source type")
    if record["is_synthetic"] != (record["source_type"] == "synthetic"):
        raise ValueError("Synthetic source flag mismatch")
    if record["is_synthetic"] and not record["scenario_version"]:
        raise ValueError("Synthetic rows must identify their scenario version")
    if record["partition"] not in {"train", "validation", "test", "challenge"}:
        raise ValueError("Unknown partition")
    if not record["record_key"] or not record["seller_group_key"]:
        raise ValueError("Stable record and seller grouping keys are required")
