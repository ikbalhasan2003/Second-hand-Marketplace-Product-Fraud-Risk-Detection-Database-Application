"""Admin HTTP/service integrity and real PostgreSQL web-role checks."""
from decimal import Decimal
from pathlib import Path
import re
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client

from accounts.models import User
from marketplace.db import actor_transaction, one, rows
from marketplace.services.listings import publish_listing
from marketplace.services.moderation import moderate_target, record_decision

pytestmark = pytest.mark.django_db


def apply_grants(root):
    with connection.cursor() as cursor:
        for name in ("008_privileges.sql", "009_app_privileges.sql"):
            script = (root / "database" / name).read_text(encoding="utf-8")
            cursor.execute(re.sub(r"^\s*(BEGIN|COMMIT);\s*$", "", script, flags=re.MULTILINE))


@pytest.fixture
def case_market():
    result = {}
    for role, key in (("seller", "seller"), ("buyer", "buyer"), ("administrator", "admin")):
        user = User.objects.create_user(f"{key}-admin-tests@example.invalid", "Stone-river-4826!pass", full_name=key.title(), location="Shanghai")
        user.groups.add(Group.objects.get(name=role))
        result[key] = user
    result["fields"] = {"title": "Admin test telescope", "description": "Working telescope with a retained description.",
                        "price": Decimal("80.00"), "category_id": one("SELECT category_id FROM categories LIMIT 1")["category_id"],
                        "condition": "good", "location": "Shanghai"}
    result["product"], _ = publish_listing(result["seller"], result["fields"])
    return result


def test_all_admin_pages_require_administrator_and_render_actual_empty_state(client, case_market):
    for path in ("/admin-app/", "/admin-app/review-queue/", "/admin-app/models/", "/admin-app/rulesets/new/", "/admin-app/audit-log/", "/admin-app/exports/"):
        assert client.get(path).status_code == 302
    client.force_login(case_market["buyer"])
    assert client.get("/admin-app/").status_code == 403
    client.force_login(case_market["admin"])
    for path in ("/admin-app/", "/admin-app/review-queue/", "/admin-app/models/", "/admin-app/rulesets/new/", "/admin-app/audit-log/", "/admin-app/exports/", f"/admin-app/cases/{case_market['product']}/"):
        assert client.get(path).status_code == 200


def test_canonical_correction_conflict_and_unresolved_export_exclusion(client, case_market):
    admin, product = case_market["admin"], case_market["product"]
    audit = record_decision(admin, product, 1, "fraud", "Evidence supports the synthetic test decision", "Reviewed test evidence")
    assert one("SELECT review_id FROM eligible_training_labels WHERE product_id=%s", [product])
    head = one("SELECT review_id FROM moderation_reviews WHERE product_id=%s", [product])["review_id"]
    with pytest.raises(ValidationError):
        record_decision(admin, product, 1, "legitimate", "Concurrent stale correction", "Test evidence", expected_head=None)
    record_decision(admin, product, 1, "unresolved", "Evidence is inconclusive after correction", "Corrected synthetic test evidence", expected_head=head)
    assert one("SELECT 1 FROM eligible_training_labels WHERE product_id=%s", [product]) is None
    assert one("SELECT count(*) AS n FROM moderation_reviews WHERE product_id=%s", [product])["n"] == 2
    client.force_login(admin)
    assert client.get(f"/admin-app/audit-log/{audit}/").status_code == 200


def test_audit_failure_rolls_back_privileged_http_mutation(client, case_market):
    with connection.cursor() as cursor:
        cursor.execute("""CREATE FUNCTION test_reject_admin_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Synthetic test audit failure'; END $$;
            CREATE TRIGGER test_admin_audit_failure BEFORE INSERT ON admin_audit_logs FOR EACH ROW EXECUTE FUNCTION test_reject_admin_audit();""")
    client.force_login(case_market["admin"])
    response = client.post(f"/admin-app/cases/{case_market['product']}/", {"operation": "moderate", "action": "remove", "expected": "visible", "reason": "Test atomic rollback"})
    assert response.status_code == 409
    assert one("SELECT visibility FROM products WHERE product_id=%s", [case_market["product"]])["visibility"] == "visible"
    assert one("SELECT count(*) AS n FROM admin_audit_logs")["n"] == 0


def test_no_score_alone_changes_visibility_or_account_and_stale_actions_fail(case_market):
    admin, product = case_market["admin"], case_market["product"]
    assert one("SELECT visibility FROM products WHERE product_id=%s", [product])["visibility"] == "visible"
    moderate_target(admin, product, "remove", "Human reviewed evidence supports removal", "visible")
    with pytest.raises(ValidationError):
        moderate_target(admin, product, "restore", "Stale browser action", "visible")
    moderate_target(admin, product, "block", "Evidence-backed account restriction", "active")
    assert one("SELECT status,is_active FROM users WHERE user_id=%s", [case_market["seller"].pk]) == {"status": "blocked", "is_active": True}


def test_web_database_process_can_run_http_workflows_without_owner_privileges(case_market, settings, tmp_path):
    """SET LOCAL ROLE is the real process group; no mocked permissions or owner bypass."""
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    settings.MEDIA_ROOT = tmp_path / "public"
    root = Path(settings.BASE_DIR)
    apply_grants(root)
    buyer_client, seller_client, admin_client, new_client = [Client() for _ in range(4)]
    for client, key in ((buyer_client, "buyer"), (seller_client, "seller"), (admin_client, "admin")):
        client.force_login(case_market[key])
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE secondhand_web")
    try:
        assert new_client.post("/buyer-app/register/", {"email": "web-role-new@example.invalid", "full_name": "Web role registration", "password": "Stone-river-4826!pass", "password_confirm": "Stone-river-4826!pass"}).status_code == 302
        assert new_client.get("/account/").status_code == 200
        assert new_client.post("/account/", {"old_password": "Stone-river-4826!pass", "new_password1": "Changed-stream-6295!pass", "new_password2": "Changed-stream-6295!pass"}).status_code == 302
        assert new_client.post("/account/enable/seller/").status_code == 302
        assert seller_client.get("/seller-app/").status_code == 200
        draft = seller_client.post("/seller-app/listings/new/", {"title": "Real process draft", "expected_revision": 0, "draft_version": 0, "action": "draft"})
        assert draft.status_code == 302
        product = case_market["product"]
        purchase = buyer_client.post(f"/buyer-app/listings/{product}/orders/", {"revision_no": 1, "request_key": str(uuid4())})
        assert purchase.status_code == 302
        report = buyer_client.post(f"/buyer-app/listings/{product}/reports/", {"revision_no": 1, "reason_code": "other", "comment": "A human test concern"})
        assert report.status_code == 302
        assert admin_client.get("/admin-app/review-queue/").status_code == 200
        decision = admin_client.post(f"/admin-app/cases/{product}/", {"operation": "decision", "revision_no": 1, "verdict": "unresolved", "reason": "Synthetic runtime test", "evidence": "Evidence is insufficient"})
        assert decision.status_code == 302
        restriction = admin_client.post(f"/admin-app/cases/{product}/", {"operation": "moderate", "action": "remove", "expected": "visible", "reason": "Human inspected synthetic evidence"})
        assert restriction.status_code == 302
        assert admin_client.get(restriction.url).status_code == 200
        with pytest.raises(DatabaseError), transaction.atomic():
            rows("INSERT INTO users_groups(user_id,group_id) SELECT %s,id FROM auth_group WHERE name='administrator'", [case_market["buyer"].pk])
        with pytest.raises(DatabaseError), transaction.atomic():
            rows("DELETE FROM admin_audit_logs")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


@pytest.fixture(scope="module")
def trained_admin_artifact(tmp_path_factory):
    """Train an actual small synthetic pipeline; never substitute invented model metadata."""
    from ml.datasets.generate import generate_records
    from ml.datasets.io import write_dataset
    from ml.training.train import train
    directory = tmp_path_factory.mktemp("admin-model")
    write_dataset(directory / "dataset", generate_records(300, 42), {
        "dataset_version": "admin-synthetic-fixture-v1", "generator_version": "scenario-v1", "seed": 42,
        "export_cutoff": "2026-12-31T00:00:00+00:00", "split_strategy": "connected groups",
        "limitations": ["Synthetic-only administrator integration test"],
        "sources": [{"source_type": "synthetic", "attribution": "Project-generated synthetic test fixture", "license_access_notes": "No personal data"}],
    })
    train(directory / "dataset", directory / "model", "admin-test-rf")
    return directory


def test_real_artifact_activation_reviewed_export_and_web_role_download(client, case_market, trained_admin_artifact, settings):
    from django.utils import timezone
    from psycopg.types.json import Jsonb
    from marketplace.services.admin_exports import create_reviewed_export
    from ml.datasets.io import load_dataset
    from ml.training.register import register
    from ml.contract import SCHEMA_VERSION
    settings.ARTIFACT_ROOT = trained_admin_artifact
    admin, product = case_market["admin"], case_market["product"]
    ids = register(connection.connection, trained_admin_artifact / "dataset", trained_admin_artifact / "model", trained_admin_artifact, admin.pk, "Register actual trained synthetic integration artifact")
    client.force_login(admin)
    response = client.post("/admin-app/models/", {"model_id": ids["model_id"], "ruleset_id": ids["ruleset_id"], "reason": "Activate verified test pipeline", "confirm": "on"})
    assert response.status_code == 302
    assert one("SELECT model_id FROM risk_models WHERE state='active'")["model_id"] == ids["model_id"]
    assert one("SELECT count(*) AS n FROM risk_rescan_campaigns")["n"] > 0
    assert client.get(f"/admin-app/models/{ids['model_id']}/").status_code == 200

    # Freeze actual facts of this single listing before the human test decision.
    claim = one("SELECT * FROM claim_risk_job(interval '5 minutes')")
    assert claim["product_id"] == product
    facts = one("""SELECT clock_timestamp() AS cutoff,greatest(p.first_published_at,r.created_at,u.created_at) AS latest,
        extract(epoch FROM(clock_timestamp()-u.created_at))/86400 AS age
        FROM products p JOIN product_revisions r ON (r.product_id,r.revision_no)=(p.product_id,p.current_revision_no)
        JOIN users u ON u.user_id=p.seller_id WHERE p.product_id=%s""", [product])
    snapshot = {"schema_version": SCHEMA_VERSION,
        "features": {"price_ratio": None, "comparable_count": 0, "price_baseline_missing": 1, "keyword_count": 0,
                     "seller_age_days": float(facts["age"]), "prior_confirmed_fraud_count": 0, "posting_frequency_7d": 1,
                     "image_count": 0, "location_difference": 0, "location_missing": 0, "duplicate_text_count_30d": 0},
        "feature_evidence": {"latest_source_at": facts["latest"].isoformat(), "point_in_time_snapshot": True}}
    with connection.cursor() as cursor:
        cursor.execute("SELECT save_risk_snapshot(%s,%s,%s,%s)", [claim["job_id"], claim["claim_token"], facts["cutoff"], Jsonb(snapshot)])
    record_decision(admin, product, 1, "legitimate", "Inspected synthetic test evidence", "Evidence-backed test decision only")
    root = Path(settings.BASE_DIR)
    apply_grants(root)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE secondhand_web")
    try:
        dataset = create_reviewed_export(admin, "reviewed-admin-fixture-v1", timezone.now(), 42, "Create reviewed export with preserved point-in-time features")
        registered = one("SELECT * FROM dataset_versions WHERE dataset_id=%s", [dataset])
        records, manifest = load_dataset(trained_admin_artifact / Path(registered["manifest_key"]).parent)
        assert len(records) == 1 and records[0]["label"] == "legitimate" and not records[0]["is_synthetic"]
        assert manifest["dataset_sha256"] == registered["dataset_sha256"]
        response = client.post(f"/admin-app/exports/{dataset}/download/", {"reason": "Verify protected research download"})
        assert response.status_code == 200 and response["X-Audit-Receipt"]
        assert response["Cache-Control"] == "private, no-store"
        assert b"records.jsonl" in b"".join(response.streaming_content)
        schema_id = one("SELECT feature_schema_id FROM risk_models WHERE model_id=%s", [ids["model_id"]])["feature_schema_id"]
        draft = client.post("/admin-app/rulesets/new/", {"version": "admin-draft-v2", "schema_id": schema_id, "medium": 45, "high": 80, "max_age_hours": 24, "reason": "Create new reviewed threshold version"})
        assert draft.status_code == 302
        assert one("SELECT 1 FROM admin_audit_logs WHERE action_type='ruleset_draft_created'")
        head = one("SELECT review_id FROM moderation_reviews WHERE product_id=%s ORDER BY review_id DESC LIMIT 1", [product])["review_id"]
        record_decision(admin, product, 1, "unresolved", "Corrected inconclusive evidence", "Updated test evidence", expected_head=head)
        with pytest.raises(ValidationError):
            create_reviewed_export(admin, "excluded-unresolved-v2", timezone.now(), 42, "Check current unresolved exclusion")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
