"""Leased, fenced PostgreSQL worker; no web request runs inference."""

from __future__ import annotations

import logging
import math
import threading
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ml.contract import SCHEMA_SHA256, SCHEMA_VERSION, validate_features
from risk.features import extract_snapshot

logger = logging.getLogger(__name__)


@contextmanager
def lease_heartbeat(dsn, job, lease_seconds):
    stop = threading.Event()
    lost = threading.Event()

    def renew():
        try:
            with psycopg.connect(dsn, autocommit=True) as connection:
                while not stop.wait(max(0.2, min(30, lease_seconds / 3))):
                    connection.execute("SELECT heartbeat_risk_job(%s,%s,%s)", (job["job_id"], job["claim_token"], timedelta(seconds=lease_seconds)))
        except Exception:
            lost.set()
            logger.warning("Risk job lease renewal stopped job_id=%s", job["job_id"])

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield lost
    finally:
        stop.set()
        thread.join(timeout=6)


class RiskWorker:
    def __init__(self, dsn: str, artifact_root: Path, lease_seconds=120):
        if not 1 <= lease_seconds <= 600:
            raise ValueError("Lease seconds must be 1..600")
        self.dsn, self.artifact_root, self.lease_seconds = dsn, Path(artifact_root), lease_seconds
        self.cache = {}

    def process_one(self) -> dict | None:
        with psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row) as connection:
            with connection.transaction():
                job = connection.execute("SELECT * FROM claim_risk_job(%s)", (timedelta(seconds=self.lease_seconds),)).fetchone()
            if not job:
                return None
            try:
                with lease_heartbeat(self.dsn, job, self.lease_seconds) as lost:
                    if job["feature_snapshot"] is None:
                        as_of, snapshot = extract_snapshot(connection, job["product_id"], job["revision_no"])
                        with connection.transaction():
                            connection.execute("SELECT save_risk_snapshot(%s,%s,%s,%s)", (job["job_id"], job["claim_token"], as_of, Jsonb(snapshot)))
                    else:
                        snapshot = job["feature_snapshot"]
                    if snapshot.get("schema_version") != SCHEMA_VERSION or snapshot["evidence"]["schema_sha256"] != SCHEMA_SHA256:
                        raise ValueError("Frozen snapshot schema mismatch")
                    validate_features(snapshot["features"])
                    model = connection.execute("""SELECT m.*,f.version AS feature_schema,f.definition FROM risk_models m
                                                 JOIN feature_schemas f USING(feature_schema_id) WHERE model_id=%s""", (job["model_id"],)).fetchone()
                    if not model or model["definition"].get("schema_sha256") != SCHEMA_SHA256:
                        raise ValueError("Registered model feature contract mismatch")
                    key = (model["model_id"], model["artifact_sha256"])
                    if key not in self.cache:
                        from ml.training.artifacts import load_trusted_pipeline

                        self.cache[key] = load_trusted_pipeline(self.artifact_root, model["artifact_key"], model["artifact_sha256"], model["feature_schema"], model["dependency_manifest"], model["class_mapping"])
                    pipeline = self.cache[key]
                    from ml.training.preprocessing import matrix

                    probability = float(pipeline.predict_proba(matrix([snapshot]))[0, list(pipeline.classes_).index(model["class_mapping"]["fraud"])])
                    if not math.isfinite(probability) or not 0 <= probability <= 1:
                        raise ValueError("Invalid model probability")
                    score = math.floor(probability * 100 + 0.5)
                    if lost.is_set():
                        raise RuntimeError("Lease renewal failed")
                    factors = observed_factors(snapshot["features"])
                    with connection.transaction():
                        risk_id = connection.execute("SELECT complete_risk_job(%s,%s,%s,%s,%s) AS risk_id", (job["job_id"], job["claim_token"], score, Jsonb(factors), Jsonb({"type": "advisory_classifier_output", "schema_version": SCHEMA_VERSION, "note": "Observed factors are contextual signals, not causal proof or a fraud verdict"}))).fetchone()["risk_id"]
                logger.info("Risk job completed job_id=%s risk_id=%s", job["job_id"], risk_id)
                return {"job_id": job["job_id"], "status": "succeeded", "risk_id": risk_id}
            except Exception as exc:
                # No raw exception, source text, storage path or credentials enter job errors/logs.
                error_code = "invalid_model_or_features" if isinstance(exc, (ValueError, FileNotFoundError)) else "worker_execution_failed"
                try:
                    with connection.transaction():
                        connection.execute("SELECT fail_risk_job(%s,%s,%s,%s)", (job["job_id"], job["claim_token"], error_code, error_code == "worker_execution_failed"))
                except psycopg.Error:
                    logger.warning("Risk job claim lost job_id=%s", job["job_id"])
                logger.warning("Risk job failed job_id=%s error_code=%s", job["job_id"], error_code)
                state = connection.execute("SELECT status FROM risk_scan_jobs WHERE job_id=%s", (job["job_id"],)).fetchone()
                return {"job_id": job["job_id"], "status": state["status"], "error_code": error_code}


def observed_factors(features):
    factors = []
    for condition, message in (
        (features["price_baseline_missing"], "Too few comparable listings for a price baseline"),
        (features["price_ratio"] is not None and features["price_ratio"] < 0.55, "Price is low relative to the selected comparable listings"),
        (features["keyword_count"] > 0, "Listing contains phrases associated with risky payment requests"),
        (features["image_count"] == 0, "No listing images are available"),
        (features["duplicate_text_count_30d"] > 0, "Similar text appears in earlier listings from this seller"),
    ):
        if condition:
            factors.append(message)
    return factors
