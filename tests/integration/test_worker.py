"""Real PostgreSQL + fitted artifact checks in an automatically isolated database."""

from pathlib import Path
import time
from uuid import uuid4

import psycopg
import pytest
from django.conf import settings
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ml.contract import text_fingerprint
from ml.datasets.generate import generate_records
from ml.datasets.io import write_dataset
from ml.training.register import register
from ml.training.train import train
from risk.features import extract_snapshot
from risk.worker import RiskWorker


@pytest.fixture(scope="module")
def isolated_worker_database(tmp_path_factory):
    database = settings.DATABASES["default"]
    base = {"host": database["HOST"], "port": database["PORT"], "user": database["USER"], "password": database["PASSWORD"]}
    name = "worker_verify_" + uuid4().hex[:12]
    owner_dsn = make_conninfo(dbname="postgres", **base)
    dsn = make_conninfo(dbname=name, **base)
    directory = tmp_path_factory.mktemp("worker-artifacts")
    with psycopg.connect(owner_dsn, autocommit=True) as owner:
        owner.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            for filename in ("001_core.sql", "002_risk.sql", "003_core_functions.sql", "004_risk_functions.sql", "005_views.sql", "006_seed.sql"):
                connection.execute((Path(settings.BASE_DIR) / "database" / filename).read_text(encoding="utf-8-sig"))
            write_dataset(directory / "dataset", generate_records(300, 42), {
                "dataset_version": "worker-synthetic-test", "generator_version": "scenario-v1", "seed": 42,
                "export_cutoff": "2026-12-31T00:00:00+00:00", "split_strategy": "connected groups",
                "limitations": ["Synthetic-only worker integration fixture"],
                "sources": [{"source_type": "synthetic", "attribution": "Project-generated test fixture", "license_access_notes": "No personal data"}],
            })
            train(directory / "dataset", directory / "model", "worker-test-rf")
            identifiers = register(connection, directory / "dataset", directory / "model", directory, 1, "Register actual synthetic test model")
            with connection.transaction():
                connection.execute("SELECT set_config('app.actor_id','1',true),set_config('app.action_reason','Activate worker verification model',true)")
                connection.execute("SELECT activate_risk_configuration(%s,%s)", (identifiers["model_id"], identifiers["ruleset_id"]))
        yield dsn, directory, identifiers
    finally:
        with psycopg.connect(owner_dsn, autocommit=True) as owner:
            owner.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_real_inference_snapshot_retry_fencing_failure_and_currentness(isolated_worker_database):
    dsn, directory, identifiers = isolated_worker_database
    worker = RiskWorker(dsn, directory)
    result = worker.process_one()
    assert result["status"] == "succeeded"
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
        job = connection.execute("SELECT * FROM risk_scan_jobs WHERE job_id=%s", (result["job_id"],)).fetchone()
        state = connection.execute("SELECT * FROM current_listing_risk WHERE product_id=%s", (job["product_id"],)).fetchone()
        assert state["assessment_state"] == "ready" and 0 <= state["risk_score"] <= 100
        assert job["feature_snapshot"]["features"]["price_ratio"] is None
        assert job["feature_snapshot"]["features"]["price_baseline_missing"] == 1
        assert connection.execute("SELECT count(*) AS n FROM risk_logs WHERE job_id=%s", (job["job_id"],)).fetchone()["n"] == 1
        # A stopped worker's old token cannot renew/finalize after lease reclamation.
        old = connection.execute("SELECT * FROM claim_risk_job(interval '1 second')").fetchone()
        as_of, snapshot = extract_snapshot(connection, old["product_id"], old["revision_no"])
        connection.execute("SELECT save_risk_snapshot(%s,%s,%s,%s)", (old["job_id"], old["claim_token"], as_of, Jsonb(snapshot)))
        time.sleep(1.1)
        # Queue sorting may pick another older queued job first; drain until reclaimed.
        claimed = []
        for _ in range(10):
            candidate = connection.execute("SELECT * FROM claim_risk_job(interval '30 seconds')").fetchone()
            if not candidate:
                break
            claimed.append(candidate)
            if candidate["job_id"] == old["job_id"]:
                break
        replacement = next(j for j in claimed if j["job_id"] == old["job_id"])
        assert replacement["claim_token"] != old["claim_token"]
        assert replacement["feature_snapshot"] == snapshot
        with pytest.raises(psycopg.Error):
            connection.execute("SELECT heartbeat_risk_job(%s,%s,interval '30 seconds')", (old["job_id"], old["claim_token"]))
        with pytest.raises(psycopg.Error):
            connection.execute("SELECT complete_risk_job(%s,%s,10,'[]',NULL)", (old["job_id"], old["claim_token"]))
        connection.execute("SELECT save_risk_snapshot(%s,%s,%s,%s)", (replacement["job_id"], replacement["claim_token"], as_of, Jsonb(snapshot)))
        connection.execute("SELECT complete_risk_job(%s,%s,10,'[]',NULL)", (replacement["job_id"], replacement["claim_token"]))
        assert connection.execute("SELECT count(*) AS n FROM risk_logs WHERE job_id=%s", (replacement["job_id"],)).fetchone()["n"] == 1
        with connection.transaction():
            connection.execute("SELECT set_config('app.actor_id','1',true),set_config('app.action_reason','Verify new rules invalidate old results',true)")
            rules = connection.execute("INSERT INTO risk_rulesets(version,feature_schema_id,created_by,max_assessment_age) SELECT 'worker-new-rules',feature_schema_id,1,interval '1 microsecond' FROM risk_models WHERE model_id=%s RETURNING ruleset_id", (identifiers["model_id"],)).fetchone()["ruleset_id"]
            connection.execute("INSERT INTO risk_rules(ruleset_id,rule_key,numeric_value,description) VALUES(%s,'medium_min',40,'Test bound'),(%s,'high_min',75,'Test bound')", (rules, rules))
            connection.execute("SELECT activate_risk_configuration(%s,%s)", (identifiers["model_id"], rules))
        outdated = connection.execute("SELECT * FROM current_listing_risk WHERE product_id=%s", (job["product_id"],)).fetchone()
        assert outdated["risk_score"] is None and outdated["assessment_state"] == "stale"
        # Retire outstanding prior claims and drain campaigns to generate a fresh current job.
        for outstanding in claimed:
            if outstanding["job_id"] != replacement["job_id"]:
                connection.execute("SELECT fail_risk_job(%s,%s,'test_interruption',false)", (outstanding["job_id"], outstanding["claim_token"]))
        for campaign in connection.execute("SELECT campaign_id FROM risk_rescan_campaigns WHERE status<>'completed' ORDER BY campaign_id").fetchall():
            connection.execute("SELECT run_rescan_batch(%s,100)", (campaign["campaign_id"],))
        # Missing registered bytes must produce failed risk rather than a low score.
        missing_root = directory / "missing-artifacts"
        missing_root.mkdir()
        failed = RiskWorker(dsn, missing_root).process_one()
        assert failed["status"] == "failed"
        failed_job = connection.execute("SELECT product_id,status,error_code FROM risk_scan_jobs WHERE job_id=%s", (failed["job_id"],)).fetchone()
        assert failed_job["status"] == "failed" and failed_job["error_code"] == "invalid_model_or_features"
        current = connection.execute("SELECT * FROM current_listing_risk WHERE product_id=%s", (failed_job["product_id"],)).fetchone()
        assert current["risk_score"] is None


def test_live_feature_selection_deduplicates_revisions_and_new_unresolved_reviews(isolated_worker_database):
    dsn, _, _ = isolated_worker_database
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
        # One product with two revisions is one comparable. Fifteen other products establish an even median after adding one more.
        with connection.transaction():
            connection.execute("SELECT set_config('app.actor_id','2',true),set_config('app.action_reason','Publish deterministic feature references',true)")
            for index in range(16):
                product = connection.execute("INSERT INTO products(seller_id) VALUES(2) RETURNING product_id").fetchone()["product_id"]
                connection.execute("""INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,price,currency,condition,location,text_fingerprint)
                                      VALUES(%s,1,5,'Reference','Ordinary reusable item',%s,'USD','like_new','Demo City',%s)""", (product, 10 + index, text_fingerprint("Reference", "Ordinary reusable item")))
                connection.execute("UPDATE products SET current_revision_no=1,availability='available' WHERE product_id=%s", (product,))
            target = connection.execute("INSERT INTO products(seller_id) VALUES(2) RETURNING product_id").fetchone()["product_id"]
            connection.execute("""INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,price,currency,condition,location,text_fingerprint)
                                  VALUES(%s,1,5,'Target','Ordinary reusable item',35,'USD','like_new','Demo City',%s)""", (target, text_fingerprint("Target", "Ordinary reusable item")))
            connection.execute("UPDATE products SET current_revision_no=1,availability='available' WHERE product_id=%s", (target,))
            # Update the most recent reference while retaining its old revision.
            connection.execute("""INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,price,currency,condition,location,text_fingerprint)
                                  SELECT product_id,2,category_id,title,description,price,currency,condition,location,text_fingerprint FROM product_revisions WHERE product_id=%s AND revision_no=1""", (product,))
            connection.execute("UPDATE products SET current_revision_no=2 WHERE product_id=%s", (product,))
        _, snapshot = extract_snapshot(connection, target, 1)
        assert snapshot["features"]["comparable_count"] == 16
        assert snapshot["evidence"]["reference_median"] == "17.50"
        assert snapshot["features"]["price_ratio"] == 2
        with connection.transaction():
            connection.execute("SELECT set_config('app.actor_id','1',true),set_config('app.action_reason','Test canonical review correction',true)")
            review = connection.execute("INSERT INTO moderation_reviews(product_id,revision_no,reviewer_id,verdict,reason,evidence_summary) VALUES(%s,2,1,'fraud','Synthetic source','Scenario asserts fraud') RETURNING review_id", (product,)).fetchone()["review_id"]
        _, prior = extract_snapshot(connection, target, 1)
        assert prior["features"]["prior_confirmed_fraud_count"] == 1
        with connection.transaction():
            connection.execute("SELECT set_config('app.actor_id','1',true),set_config('app.action_reason','Synthetic unresolved correction',true)")
            connection.execute("INSERT INTO moderation_reviews(product_id,revision_no,reviewer_id,verdict,reason,evidence_summary,supersedes_review_id) VALUES(%s,2,1,'unresolved','Need evidence','Synthetic uncertainty',%s)", (product, review))
        _, corrected = extract_snapshot(connection, target, 1)
        assert corrected["features"]["prior_confirmed_fraud_count"] == 0
        connection.execute("UPDATE users SET location=NULL WHERE user_id=2")
        _, missing_location = extract_snapshot(connection, target, 1)
        assert missing_location["features"]["location_difference"] is None
        assert missing_location["features"]["location_missing"] == 1
        # Mutable locations must be frozen at extraction time; old snapshots remain intact.
        assert snapshot["evidence"]["seller_location_observed"] == "Demo City"
        assert missing_location["evidence"]["seller_location_observed"] is None
