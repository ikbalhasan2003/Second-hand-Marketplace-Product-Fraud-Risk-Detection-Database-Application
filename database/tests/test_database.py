"""PostgreSQL integration tests; run only against a disposable EMPTY database.

DATABASE_TEST_DSN must name an already-created database owned by the test user.
The suite refuses to install over existing public tables. It installs001..006,
rolls ordinary tests back, and leaves its schema/seed plus the final race fixture.
AI metadata below is deliberately non-loadable schema-test data. No model is run,
and fixture confusion counts are not measured machine-learning results.
"""

import hashlib
import os
from pathlib import Path
import threading
import unittest
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


DATABASE_DIR = Path(__file__).resolve().parents[1]
INSTALL_FILES = (
    "001_core.sql", "002_risk.sql", "003_core_functions.sql",
    "004_risk_functions.sql", "005_views.sql", "006_seed.sql",
)


class DatabaseIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("DATABASE_TEST_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("Set DATABASE_TEST_DSN to a disposable EMPTY PostgreSQL database")
        with psycopg.connect(cls.dsn, autocommit=True) as connection:
            table_count = connection.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            ).fetchone()[0]
            if table_count:
                raise RuntimeError("Refusing to install: test database already has public tables")
            for name in INSTALL_FILES:
                connection.execute((DATABASE_DIR / name).read_text(encoding="utf-8-sig"))

    def setUp(self):
        self.connection = psycopg.connect(self.dsn, row_factory=dict_row)
        self.actor(1)
        self.connection.execute("SET LOCAL lock_timeout = '5s'")

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()

    def actor(self, user_id):
        self.connection.execute(
            "SELECT set_config('app.actor_id',%s,true),"
            "set_config('app.action_reason','Database regression test',true)",
            (str(user_id),),
        )

    def one(self, sql, parameters=None):
        return self.connection.execute(sql, parameters).fetchone()

    def scalar(self, sql, parameters=None):
        row = self.one(sql, parameters)
        return next(iter(row.values())) if row is not None else None

    def assert_sql_fails(self, sql, parameters=None, sqlstate=None):
        # A nested transaction is a SAVEPOINT, keeping the containing test usable.
        with self.assertRaises(psycopg.Error) as caught:
            with self.connection.transaction():
                self.connection.execute(sql, parameters)
        if sqlstate:
            self.assertEqual(caught.exception.sqlstate, sqlstate)

    def new_revision(self, product_id=102, revision_no=2):
        self.actor(2)
        self.connection.execute(
            """INSERT INTO product_revisions(product_id,revision_no,category_id,title,
                   description,price,currency,condition,location,text_fingerprint)
               SELECT product_id,%s,category_id,title || ' revised',description,price,
                      currency,condition,location,repeat('a',64)
               FROM product_revisions WHERE product_id=%s AND revision_no=1""",
            (revision_no, product_id),
        )

    def configure_schema_test_model(self):
        """Activate non-loadable metadata solely to exercise relational workflows."""
        self.actor(1)
        version = self._testMethodName
        schema_id = self.scalar(
            """INSERT INTO feature_schemas(version,definition,code_revision)
               VALUES(%s,%s,'schema-test-only') RETURNING feature_schema_id""",
            (version, Jsonb({"purpose": "schema-test-only", "features": ["x"]})),
        )
        dataset_id = self.scalar(
            """INSERT INTO dataset_versions(version,feature_schema_id,seed,export_cutoff,
                       split_strategy,created_by)
               VALUES(%s,%s,7,clock_timestamp(),'schema-test-only; no training data',1)
               RETURNING dataset_id""",
            (version, schema_id),
        )
        self.connection.execute(
            """UPDATE dataset_versions SET state='frozen',frozen_at=clock_timestamp(),
                   manifest_key='schema-tests/not-a-training-dataset.json',dataset_sha256=repeat('0',64)
               WHERE dataset_id=%s""", (dataset_id,),
        )
        model_id = self.scalar(
            """INSERT INTO risk_models(version,feature_schema_id,dataset_id,algorithm,
                       artifact_key,artifact_sha256,seed,class_mapping,dependency_manifest,
                       code_revision,registered_by)
               VALUES(%s,%s,%s,'random_forest',%s,repeat('0',64),7,%s,%s,'schema-test-only',1)
               RETURNING model_id""",
            (version, schema_id, dataset_id, "schema-tests/not-a-loadable-model-" + version,
             Jsonb({"fraud": 1, "legitimate": 0}), Jsonb({"purpose": "schema-test-only"})),
        )
        self.connection.execute(
            """INSERT INTO model_evaluations(model_id,partition,slice_key,sample_count,fraud_count,
                       true_positive,false_positive,true_negative,false_negative,report_key)
               VALUES(%s,'validation','schema-fixture-not-measured',1,1,1,0,0,0,
                      'schema-tests/not-an-evaluation.json')""", (model_id,),
        )
        ruleset_id = self.scalar(
            """INSERT INTO risk_rulesets(version,feature_schema_id,created_by)
               VALUES(%s,%s,1) RETURNING ruleset_id""", (version, schema_id),
        )
        self.connection.execute(
            """INSERT INTO risk_rules(ruleset_id,rule_key,numeric_value,description)
               VALUES(%s,'medium_min',40,'schema fixture'),(%s,'high_min',75,'schema fixture')""",
            (ruleset_id, ruleset_id),
        )
        self.connection.execute("SELECT activate_risk_configuration(%s,%s)", (model_id, ruleset_id))
        # Isolate product102 for worker API tests without sleeping or consuming jobs.
        self.connection.execute(
            """UPDATE risk_scan_jobs SET retry_at=clock_timestamp()+interval '1 day'
               WHERE product_id<>102 AND status='queued'"""
        )
        return schema_id, dataset_id, model_id, ruleset_id

    def claim(self):
        job = self.one("SELECT * FROM claim_risk_job()")
        self.assertIsNotNone(job)
        self.assertEqual(job["product_id"], 102)
        return job

    def save_snapshot(self, job, *, old=False):
        snapshot_time = self.scalar(
            "SELECT clock_timestamp()-interval '25 hours'" if old else "SELECT clock_timestamp()"
        )
        self.connection.execute(
            "SELECT save_risk_snapshot(%s,%s,%s,%s)",
            (job["job_id"], job["claim_token"], snapshot_time, Jsonb({"x": 1})),
        )
        return snapshot_time

    def finish(self, job, score=20):
        return self.scalar(
            "SELECT complete_risk_job(%s,%s,%s)",
            (job["job_id"], job["claim_token"], score),
        )

    def test_01_identity_and_role_constraints(self):
        self.assert_sql_fails(
            "INSERT INTO users(email,password,full_name) VALUES('SELLER@EXAMPLE.INVALID','!','Duplicate')",
            sqlstate="23505",
        )
        self.assert_sql_fails("INSERT INTO users_groups(user_id,group_id) VALUES(3,3)", sqlstate="23514")
        self.assert_sql_fails("UPDATE users SET created_at=created_at-interval '1 day' WHERE user_id=2")

    def test_02_price_and_revision_constraints(self):
        self.actor(2)
        self.assert_sql_fails(
            """INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,
                   price,currency,condition,location,text_fingerprint)
               VALUES(102,2,1,'Invalid price','Schema test',0,'USD','good','Demo City',repeat('a',64))""",
            sqlstate="23514",
        )
        with self.assertRaises(psycopg.Error) as caught:
            with self.connection.transaction():
                self.connection.execute("UPDATE products SET current_revision_no=999 WHERE product_id=102")
                self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.assertEqual(caught.exception.sqlstate, "23503")

    def test_03_order_request_replay_and_conflict(self):
        self.actor(3)
        order = self.one("SELECT * FROM transactions WHERE transaction_id=100")
        history_count = self.scalar("SELECT count(*) FROM order_status_history WHERE transaction_id=100")
        result = self.scalar(
            "SELECT place_order(3,100,1,%s,%s)",
            (order["request_key"], order["request_fingerprint"]),
        )
        self.assertEqual(result, 100)
        self.assertEqual(self.scalar("SELECT count(*) FROM order_status_history WHERE transaction_id=100"), history_count)
        self.assert_sql_fails(
            "SELECT place_order(3,100,1,%s,%s)", (order["request_key"], "b" * 64), sqlstate="23514",
        )
        self.actor(4)
        self.assert_sql_fails("SELECT place_order(4,100,1,%s,%s)", (uuid.uuid4(), "c" * 64))

    def test_04_order_state_machine_and_terminal_sale(self):
        self.actor(3)
        self.assert_sql_fails("SELECT transition_order(100,'shipped')", sqlstate="23514")
        self.actor(2)
        self.connection.execute("SELECT transition_order(100,'accepted')")
        self.actor(3)
        self.connection.execute("SELECT transition_order(100,'completed')")
        self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.assertEqual(self.scalar("SELECT availability FROM products WHERE product_id=100"), "sold")
        self.assert_sql_fails("SELECT transition_order(100,'cancelled')", sqlstate="23514")
        self.actor(4)
        self.assert_sql_fails("SELECT place_order(4,100,1,%s,%s)", (uuid.uuid4(), "d" * 64))

    def test_05_cancellation_preserves_admin_removal(self):
        self.connection.execute("UPDATE products SET visibility='removed_by_admin' WHERE product_id=100")
        self.actor(3)
        self.connection.execute("SELECT transition_order(100,'cancelled')")
        self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        row = self.one("SELECT availability,visibility FROM products WHERE product_id=100")
        self.assertEqual(row, {"availability": "available", "visibility": "removed_by_admin"})
        self.actor(4)
        self.assert_sql_fails("SELECT place_order(4,100,1,%s,%s)", (uuid.uuid4(), "e" * 64))

    def test_06_purchase_and_report_targets_are_immutable(self):
        self.actor(2)
        self.assert_sql_fails("UPDATE products SET seller_id=3 WHERE product_id=102", sqlstate="23514")
        self.assert_sql_fails("UPDATE product_revisions SET price=1 WHERE product_id=100 AND revision_no=1", sqlstate="23514")
        self.assert_sql_fails(
            """INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,
                   price,currency,condition,location,text_fingerprint)
               VALUES(100,2,1,'Forbidden edit','Schema test',1,'USD','good','Demo City',repeat('a',64))""",
            sqlstate="23514",
        )
        self.actor(4)
        self.assert_sql_fails(
            """INSERT INTO fraud_reports(product_id,revision_no,reporter_id,transaction_id,reason_code,comment)
               VALUES(101,1,4,100,'other','Wrong product and buyer for this order')""", sqlstate="23503",
        )
        self.assert_sql_fails(
            """INSERT INTO fraud_reports(product_id,revision_no,reporter_id,transaction_id,reason_code,comment)
               VALUES(100,1,4,100,'other','Correct product, unrelated order buyer')""", sqlstate="23503",
        )

    def test_07_sealed_images_and_append_only_history(self):
        self.actor(2)
        self.assert_sql_fails(
            """INSERT INTO product_images(product_id,revision_no,storage_key,sort_order,content_type,
                   byte_size,content_sha256,width,height)
               VALUES(102,1,'schema-tests/no-real-file.jpg',0,'image/jpeg',100,repeat('0',64),1,1)""",
            sqlstate="23514",
        )
        self.new_revision()
        image_id = self.scalar(
            """INSERT INTO product_images(product_id,revision_no,storage_key,sort_order,content_type,
                   byte_size,content_sha256,width,height)
               VALUES(102,2,'schema-tests/no-real-file.jpg',0,'image/jpeg',100,repeat('0',64),1,1)
               RETURNING image_id"""
        )
        self.assert_sql_fails("UPDATE product_images SET byte_size=200 WHERE image_id=%s", (image_id,), sqlstate="23514")
        self.assert_sql_fails("UPDATE order_status_history SET reason='Changed' WHERE transaction_id=100", sqlstate="23514")
        self.assert_sql_fails("DELETE FROM admin_audit_logs", sqlstate="23514")

    def test_08_canonical_unresolved_correction_removes_label(self):
        old_time = self.scalar("SELECT reviewed_at FROM moderation_reviews WHERE review_id=100")
        self.assert_sql_fails(
            """INSERT INTO moderation_reviews(product_id,revision_no,reviewer_id,verdict,reason,evidence_summary)
               VALUES(101,1,1,'fraud','Competing root','Schema test')""", sqlstate="23514",
        )
        correction_id = self.scalar(
            """INSERT INTO moderation_reviews(product_id,revision_no,report_id,reviewer_id,
                       verdict,reason,evidence_summary,supersedes_review_id)
               VALUES(101,1,100,1,'unresolved','Synthetic evidence is inconclusive','Schema test',100)
               RETURNING review_id"""
        )
        # statement_timestamp() advances per query, so the new decision is visible.
        self.assertEqual(self.scalar("SELECT review_id FROM latest_effective_reviews WHERE product_id=101"), correction_id)
        self.assertEqual(self.scalar("SELECT count(*) FROM eligible_training_labels WHERE product_id=101"), 0)
        self.assertEqual(self.scalar("SELECT review_id FROM effective_reviews_at(%s) WHERE product_id=101", (old_time,)), 100)
        self.assert_sql_fails(
            """INSERT INTO moderation_reviews(product_id,revision_no,reviewer_id,verdict,
                       reason,evidence_summary,supersedes_review_id)
               VALUES(101,1,1,'fraud','Stale predecessor','Schema test',100)""", sqlstate="23514",
        )
        self.assert_sql_fails(
            """INSERT INTO moderation_reviews(product_id,revision_no,report_id,reviewer_id,
                       verdict,reason,evidence_summary)
               VALUES(102,1,100,1,'unresolved','Cross-target report','Schema test')""", sqlstate="23503",
        )

    def test_09_message_participants_and_receipts(self):
        self.actor(4)
        self.assert_sql_fails(
            "INSERT INTO chat_messages(conversation_id,sender_id,message_text) VALUES(100,4,'Intrusion')", sqlstate="42501",
        )
        message_id = self.scalar("SELECT min(message_id) FROM chat_messages WHERE conversation_id=100 AND sender_id=3")
        self.assert_sql_fails("UPDATE chat_messages SET read_at=clock_timestamp() WHERE message_id=%s", (message_id,), sqlstate="42501")
        self.actor(2)
        self.connection.execute("UPDATE chat_messages SET read_at=clock_timestamp() WHERE message_id=%s", (message_id,))
        self.assertIsNotNone(self.scalar("SELECT read_at FROM chat_messages WHERE message_id=%s", (message_id,)))
        self.actor(1)
        self.connection.execute("UPDATE users SET status='blocked' WHERE user_id=3")
        self.actor(3)
        self.assert_sql_fails(
            "INSERT INTO chat_messages(conversation_id,sender_id,message_text) VALUES(100,3,'Blocked send')", sqlstate="42501",
        )

    def test_10_audit_failure_rolls_back_privileged_change(self):
        audit_count = self.scalar("SELECT count(*) FROM admin_audit_logs")
        self.connection.execute("""CREATE FUNCTION regression_reject_audit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Forced audit failure'; END $$""")
        self.connection.execute("""CREATE TRIGGER regression_audit_failure BEFORE INSERT ON admin_audit_logs
            FOR EACH ROW EXECUTE FUNCTION regression_reject_audit()""")
        self.assert_sql_fails("UPDATE products SET visibility='removed_by_admin' WHERE product_id=102")
        self.assertEqual(self.scalar("SELECT visibility FROM products WHERE product_id=102"), "visible")
        self.assertEqual(self.scalar("SELECT count(*) FROM admin_audit_logs"), audit_count)

    def test_11_unbound_scan_is_pending_without_numeric_default(self):
        self.assertIsNone(self.one("SELECT * FROM claim_risk_job()"))
        row = self.one("SELECT assessment_state,risk_score,risk_level FROM current_listing_risk WHERE product_id=102")
        self.assertEqual(row, {"assessment_state": "pending", "risk_score": None, "risk_level": None})
        self.assertEqual(self.scalar("SELECT count(*) FROM risk_scan_jobs WHERE attempts<>0"), 0)

    def test_12_scan_completion_is_atomic_and_deduplicated(self):
        self.configure_schema_test_model()
        job = self.claim()
        self.save_snapshot(job)
        risk_id = self.finish(job)
        self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.assertEqual(self.scalar("SELECT count(*) FROM risk_logs WHERE job_id=%s", (job["job_id"],)), 1)
        row = self.one("SELECT assessment_state,risk_id,risk_score,risk_level FROM current_listing_risk WHERE product_id=102")
        self.assertEqual(row, {"assessment_state": "ready", "risk_id": risk_id, "risk_score": 20, "risk_level": "low"})
        self.assert_sql_fails("SELECT complete_risk_job(%s,%s,20)", (job["job_id"], job["claim_token"]), sqlstate="55000")
        self.assert_sql_fails("UPDATE risk_logs SET risk_score=0 WHERE risk_id=%s", (risk_id,))

    def test_13_expired_and_replaced_claims_cannot_write(self):
        self.configure_schema_test_model()
        old_job = self.claim()
        snapshot_time = self.save_snapshot(old_job)
        # Test-owner clock fixture: expire the persisted lease, without wall-clock sleeps.
        self.connection.execute(
            "UPDATE risk_scan_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id=%s",
            (old_job["job_id"],),
        )
        self.assert_sql_fails("SELECT heartbeat_risk_job(%s,%s)", (old_job["job_id"], old_job["claim_token"]), sqlstate="55000")
        new_job = self.claim()
        self.assertEqual(new_job["job_id"], old_job["job_id"])
        self.assertEqual(new_job["attempts"], 2)
        self.assertNotEqual(new_job["claim_token"], old_job["claim_token"])
        self.assertEqual(new_job["feature_as_of"], snapshot_time)
        self.assert_sql_fails("SELECT complete_risk_job(%s,%s,20)", (old_job["job_id"], old_job["claim_token"]), sqlstate="55000")
        self.assert_sql_fails(
            "SELECT save_risk_snapshot(%s,%s,%s,%s)",
            (new_job["job_id"], new_job["claim_token"], snapshot_time, Jsonb({"x": 2})),
        )
        self.finish(new_job)
        self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_14_snapshot_age_invalidates_score_at_read_time(self):
        self.configure_schema_test_model()
        job = self.claim()
        self.save_snapshot(job, old=True)
        self.finish(job)
        row = self.one("SELECT assessment_state,risk_score,risk_level FROM current_listing_risk WHERE product_id=102")
        self.assertEqual(row, {"assessment_state": "stale", "risk_score": None, "risk_level": None})

    def test_15_revision_context_and_model_invalidate_scores(self):
        self.configure_schema_test_model()
        job = self.claim()
        self.save_snapshot(job)
        self.finish(job)
        with self.connection.transaction():
            self.connection.execute("UPDATE products SET context_version=context_version+1 WHERE product_id=102")
            self.assertEqual(self.scalar("SELECT assessment_state FROM current_listing_risk WHERE product_id=102"), "pending")
            self.assertIsNone(self.scalar("SELECT risk_score FROM current_listing_risk WHERE product_id=102"))
            # Undo this branch to isolate the next invalidation condition.
            raise psycopg.Rollback()
        with self.connection.transaction():
            self.new_revision()
            self.connection.execute("UPDATE products SET current_revision_no=2 WHERE product_id=102")
            self.assertIsNone(self.scalar("SELECT risk_score FROM current_listing_risk WHERE product_id=102"))
            raise psycopg.Rollback()
        self.actor(1)
        self.connection.execute("UPDATE risk_models SET state='retired' WHERE state='active'")
        self.assertEqual(self.scalar("SELECT assessment_state FROM current_listing_risk WHERE product_id=102"), "stale")
        self.assertIsNone(self.scalar("SELECT risk_score FROM current_listing_risk WHERE product_id=102"))

    def test_16_permanent_failure_has_no_low_risk_badge(self):
        self.configure_schema_test_model()
        job = self.claim()
        self.connection.execute("SELECT fail_risk_job(%s,%s,'schema_test_failure',false)", (job["job_id"], job["claim_token"]))
        row = self.one("SELECT assessment_state,risk_score,risk_level FROM current_listing_risk WHERE product_id=102")
        self.assertEqual(row, {"assessment_state": "failed", "risk_score": None, "risk_level": None})

    def test_17_daily_campaign_replay_advances_context_once(self):
        before = {
            row["product_id"]: row["context_version"]
            for row in self.connection.execute("SELECT product_id,context_version FROM products WHERE availability='available'")
        }
        campaign_id = self.scalar("SELECT create_daily_rescan(DATE '2026-11-03','Asia/Shanghai')")
        self.assertEqual(self.scalar("SELECT create_daily_rescan(DATE '2026-11-03','Asia/Shanghai')"), campaign_id)
        processed = self.scalar("SELECT run_rescan_batch(%s,100)", (campaign_id,))
        self.assertEqual(processed, len(before))
        self.assertEqual(self.scalar("SELECT run_rescan_batch(%s,100)", (campaign_id,)), 0)
        self.assertEqual(self.scalar("SELECT count(*) FROM risk_rescan_events WHERE campaign_id=%s", (campaign_id,)), len(before))
        for product_id, context in before.items():
            self.assertEqual(self.scalar("SELECT context_version FROM products WHERE product_id=%s", (product_id,)), context + 1)
        self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_18_frozen_metadata_and_published_rules_are_immutable(self):
        schema_id, dataset_id, model_id, ruleset_id = self.configure_schema_test_model()
        self.assert_sql_fails("UPDATE feature_schemas SET definition='{}' WHERE feature_schema_id=%s", (schema_id,))
        self.assert_sql_fails("UPDATE dataset_versions SET seed=8 WHERE dataset_id=%s", (dataset_id,))
        self.assert_sql_fails("UPDATE risk_models SET artifact_key='changed' WHERE model_id=%s", (model_id,))
        self.assert_sql_fails("UPDATE risk_rules SET numeric_value=1 WHERE ruleset_id=%s", (ruleset_id,))

    def test_19_dataset_freeze_rejects_cross_partition_seller_leakage(self):
        schema_id, _, _, _ = self.configure_schema_test_model()
        dataset_id = self.scalar(
            """INSERT INTO dataset_versions(version,feature_schema_id,seed,export_cutoff,split_strategy,created_by)
               VALUES('schema-leakage-fixture',%s,7,clock_timestamp(),'seller grouping',1) RETURNING dataset_id""",
            (schema_id,),
        )
        source_id = self.scalar(
            """INSERT INTO dataset_sources(source_key,source_type,attribution,license_access_notes)
               VALUES('schema-leakage-fixture','synthetic','Unit-test scenario','No external dataset') RETURNING source_id"""
        )
        for index, partition in enumerate(("train", "test")):
            group_id = self.scalar(
                """INSERT INTO dataset_split_groups(dataset_id,group_key,partition)
                   VALUES(%s,%s,%s) RETURNING split_group_id""", (dataset_id, f"group-{index}", partition),
            )
            self.connection.execute(
                """INSERT INTO dataset_records(dataset_id,record_key,source_id,split_group_id,seller_group_key,
                       feature_as_of,feature_values,label,label_source,label_decided_at,is_synthetic,scenario_version)
                   VALUES(%s,%s,%s,%s,'same-synthetic-seller',clock_timestamp()-interval '2 hours',%s,
                          'legitimate','schema fixture',clock_timestamp()-interval '1 hour',true,'schema-test-only')""",
                (dataset_id, f"record-{index}", source_id, group_id, Jsonb({"x": index})),
            )
        self.assert_sql_fails(
            """UPDATE dataset_versions SET state='frozen',frozen_at=clock_timestamp(),
                   manifest_key='schema-tests/no-real-export.json',dataset_sha256=repeat('0',64)
               WHERE dataset_id=%s""", (dataset_id,),
        )
        self.assertEqual(self.scalar("SELECT state FROM dataset_versions WHERE dataset_id=%s", (dataset_id,)), "building")

    def test_20_bound_and_unbound_job_deduplication(self):
        self.assert_sql_fails(
            """INSERT INTO risk_scan_jobs(product_id,revision_no,context_version)
               SELECT product_id,current_revision_no,context_version FROM products WHERE product_id=102""",
            sqlstate="23505",
        )
        _, _, model_id, _ = self.configure_schema_test_model()
        self.assert_sql_fails(
            """INSERT INTO risk_scan_jobs(product_id,revision_no,context_version,model_id)
               SELECT product_id,current_revision_no,context_version,%s FROM products WHERE product_id=102""",
            (model_id,),
        )
        job = self.claim()
        self.assert_sql_fails(
            """INSERT INTO risk_scan_jobs(product_id,revision_no,context_version,model_id,ruleset_id,feature_schema_id)
               SELECT product_id,revision_no,context_version,model_id,ruleset_id,feature_schema_id
               FROM risk_scan_jobs WHERE job_id=%s""", (job["job_id"],), sqlstate="23505",
        )

    def test_21_nonowner_cannot_publish_saved_revision(self):
        self.new_revision()
        self.actor(3)
        self.assert_sql_fails("UPDATE products SET current_revision_no=2 WHERE product_id=102", sqlstate="42501")

    def test_22_blocked_seller_can_complete_existing_obligations(self):
        self.connection.execute("UPDATE users SET status='blocked' WHERE user_id=2")
        self.actor(2)
        self.connection.execute("SELECT transition_order(100,'accepted')")
        self.actor(3)
        self.connection.execute("SELECT transition_order(100,'completed')")
        self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.assertEqual(self.scalar("SELECT status FROM transactions WHERE transaction_id=100"), "completed")

    def test_23_configured_expiry_only_cancels_unanswered_orders(self):
        self.connection.execute("UPDATE marketplace_settings SET unanswered_order_timeout=interval '1 microsecond'")
        self.connection.execute("UPDATE products SET visibility='removed_by_admin' WHERE product_id=100")
        self.assertEqual(self.scalar("SELECT expire_unanswered_orders(10)"), 1)
        self.assertEqual(self.scalar("SELECT status FROM transactions WHERE transaction_id=100"), "cancelled")
        state = self.one("SELECT availability,visibility FROM products WHERE product_id=100")
        self.assertEqual((state["availability"], state["visibility"]), ("available", "removed_by_admin"))
        self.assertEqual(self.scalar("SELECT system_actor FROM order_status_history WHERE transaction_id=100 ORDER BY event_id DESC LIMIT 1"), "order_expiry")
        self.assertEqual(self.scalar("SELECT expire_unanswered_orders(10)"), 0)
        self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_24_marketplace_currency_is_consistent(self):
        self.assert_sql_fails("UPDATE marketplace_settings SET currency='EUR'")
        self.actor(2)
        self.assert_sql_fails(
            """INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,
                       price,currency,condition,location,text_fingerprint)
               VALUES(102,2,1,'Wrong currency','Synthetic database fixture',10,
                      'EUR','good','Demo City',repeat('a',64))""", sqlstate="23514",
        )

    def test_99_two_connections_compete_for_one_product(self):
        # Commit a dedicated fixture; all earlier tests are fully rolled back.
        self.actor(2)
        product_id = self.scalar("INSERT INTO products(seller_id) VALUES(2) RETURNING product_id")
        self.connection.execute(
            """INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,
                       price,currency,condition,location,text_fingerprint)
               VALUES(%s,1,1,'Purchase race fixture','Synthetic database concurrency fixture',10,
                      'USD','good','Demo City',repeat('f',64))""", (product_id,),
        )
        self.connection.execute("UPDATE products SET current_revision_no=1,availability='available' WHERE product_id=%s", (product_id,))
        self.connection.commit()
        barrier = threading.Barrier(2, timeout=10)
        outcomes = []
        outcomes_lock = threading.Lock()

        def purchase(buyer_id):
            outcome = None
            try:
                with psycopg.connect(self.dsn) as connection:
                    connection.execute("SELECT set_config('app.actor_id',%s,true)", (str(buyer_id),))
                    connection.execute("SET LOCAL lock_timeout = '5s'")
                    fingerprint = hashlib.sha256(f"{buyer_id}:{product_id}:1".encode()).hexdigest()
                    barrier.wait()
                    order_id = connection.execute(
                        "SELECT place_order(%s,%s,1,%s,%s)",
                        (buyer_id, product_id, uuid.uuid4(), fingerprint),
                    ).fetchone()[0]
                outcome = ("committed", order_id)
            except psycopg.Error as error:
                outcome = ("rejected", error.sqlstate)
            except Exception as error:  # Propagate worker/thread failures to unittest.
                outcome = ("unexpected", repr(error))
            finally:
                with outcomes_lock:
                    outcomes.append(outcome)

        threads = [threading.Thread(target=purchase, args=(buyer,), daemon=True) for buyer in (3, 4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "Purchase threads did not finish")
        self.assertEqual(sum(item[0] == "committed" for item in outcomes), 1, outcomes)
        self.assertEqual(sum(item == ("rejected", "23514") for item in outcomes), 1, outcomes)
        self.assertEqual(self.scalar("SELECT count(*) FROM transactions WHERE product_id=%s AND status<>'cancelled'", (product_id,)), 1)
        self.assertEqual(self.scalar("SELECT availability FROM products WHERE product_id=%s", (product_id,)), "reserved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
