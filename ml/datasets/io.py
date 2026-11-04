"""Canonical JSONL datasets and checksummed, write-once manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ml.contract import FEATURE_NAMES, SCHEMA_DEFINITION, SCHEMA_SHA256, SCHEMA_VERSION, validate_record


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_partitions(records: list[dict]) -> None:
    keys = set()
    groups = {}
    for record in records:
        if record["record_key"] in keys:
            raise ValueError("Duplicate record key")
        keys.add(record["record_key"])
        for name in ("seller_group_key", "template_family_key", "duplicate_group_key"):
            value = record[name]
            if value:
                key = (name, value)
                old = groups.setdefault(key, record["partition"])
                if old != record["partition"]:
                    raise ValueError(f"Related-record partition leakage: {name}")


def write_dataset(directory: Path, records: list[dict], metadata: dict) -> dict:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    cutoff = metadata["export_cutoff"]
    try:
        for record in records:
            validate_record(record, cutoff)
        validate_partitions(records)
        path = directory / "records.jsonl"
        with path.open("x", encoding="utf-8", newline="\n") as output:
            for record in sorted(records, key=lambda r: r["record_key"]):
                output.write(canonical_json(record) + "\n")
        manifest = {
            **metadata, "format": "marketplace-jsonl-v1", "feature_schema": SCHEMA_VERSION,
            "feature_schema_sha256": SCHEMA_SHA256, "feature_schema_definition": SCHEMA_DEFINITION,
            "predictor_order": list(FEATURE_NAMES), "record_count": len(records),
            "dataset_sha256": checksum(path), "partitions": {},
            "synthetic_only": all(r["is_synthetic"] for r in records),
            "split_manifest": {r["record_key"]: r["partition"] for r in records},
        }
        for partition in ("train", "validation", "test", "challenge"):
            subset = [r for r in records if r["partition"] == partition]
            manifest["partitions"][partition] = {
                "sample_count": len(subset), "fraud_count": sum(r["label"] == "fraud" for r in subset),
            }
        (directory / "manifest.json").write_text(canonical_json(manifest) + "\n", encoding="utf-8")
        return manifest
    except Exception:
        # Leave any partial output for diagnosis, never silently replace an immutable dataset.
        raise


def load_dataset(directory: Path) -> tuple[list[dict], dict]:
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["feature_schema"] != SCHEMA_VERSION or manifest["predictor_order"] != list(FEATURE_NAMES):
        raise ValueError("Dataset predictor contract mismatch")
    if manifest.get("feature_schema_sha256") != SCHEMA_SHA256 or manifest.get("feature_schema_definition") != SCHEMA_DEFINITION:
        raise ValueError("Dataset feature definition mismatch")
    path = directory / "records.jsonl"
    if checksum(path) != manifest["dataset_sha256"]:
        raise ValueError("Dataset checksum mismatch")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(records) != manifest["record_count"]:
        raise ValueError("Dataset row count mismatch")
    for record in records:
        validate_record(record, manifest["export_cutoff"])
        if manifest["split_manifest"].get(record["record_key"]) != record["partition"]:
            raise ValueError("Split manifest mismatch")
    validate_partitions(records)
    return records, manifest
