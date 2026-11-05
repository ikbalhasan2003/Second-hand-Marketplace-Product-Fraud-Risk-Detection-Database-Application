"""Admin HTTP/service integrity and real PostgreSQL web-role checks."""
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
from threading import Barrier
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import DatabaseError, close_old_connections, connection, transaction
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


@pytest.mark.parametrize("identity", ["buyer", "seller", "blocked_admin"])
def test_privileged_posts_reject_nonadministrators_and_blocked_admins(client, case_market, identity):
    user = case_market["admin" if identity == "blocked_admin" else identity]
    if identity == "blocked_admin":
        operator = User.objects.create_user("operator@example.invalid", full_name="Operator")
        operator.groups.add(Group.objects.get(name="administrator"))
        with actor_transaction(operator, "Restrict test administrator"):
            rows("UPDATE users SET status='blocked' WHERE user_id=%s", [user.pk])
    client.force_login(user)
    product = case_market["product"]
    for path in (f"/admin-app/cases/{product}/", "/admin-app/models/", "/admin-app/rulesets/new/",
                 "/admin-app/exports/", "/admin-app/exports/1/download/", "/admin-app/disputes/1/"):
        assert client.post(path, {"operation": "decision", "revision_no": 1, "verdict": "fraud",
                                  "reason": "Unauthorized attempt", "evidence": "Test"}).status_code == 403
    assert one("SELECT count(*) AS n FROM moderation_reviews WHERE product_id=%s", [product])["n"] == 0


def test_admin_private_pages_prevent_caching(client, case_market):
    client.force_login(case_market["admin"])
    for path in ("/admin-app/", "/admin-app/review-queue/", "/admin-app/exports/",
                 f"/admin-app/cases/{case_market['product']}/"):
        response = client.get(path)
        assert response.status_code == 200
        assert "no-store" in response["Cache-Control"]
        assert "private" in response["Cache-Control"]


def test_queue_deduplicates_reports_and_retains_dispute_filter_when_paging(client, case_market):
    product = case_market["product"]
    with actor_transaction(case_market["buyer"]):
        for _ in range(2):
            rows("""INSERT INTO fraud_reports(product_id,revision_no,reporter_id,reason_code,comment)
                VALUES(%s,1,%s,'other','Synthetic concern')""", [product, case_market["buyer"].pk])
    client.force_login(case_market["admin"])
    response = client.get("/admin-app/review-queue/?source=reports")
    cases = response.context["cases"]
    assert len(cases) == 1 and cases[0]["open_report_count"] == 2
    assert cases[0]["reported_revision_nos"] == [1]
    response = client.get("/admin-app/review-queue/?type=order-dispute&dispute_page=2")
    assert not response.context["cases"]
    assert "type=order-dispute" in response.context["query"]
    assert response.context["dispute_page"].paginator.per_page == 25


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


def test_decision_audit_failure_rolls_back_chain_and_label(case_market):
    admin, product = case_market["admin"], case_market["product"]
    record_decision(admin, product, 1, "legitimate", "Reviewed synthetic listing", "Synthetic evidence")
    head = one("SELECT review_id FROM eligible_training_labels WHERE product_id=%s", [product])["review_id"]
    with connection.cursor() as cursor:
        cursor.execute("""CREATE FUNCTION reject_correction_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Synthetic audit failure'; END $$;
            CREATE TRIGGER correction_audit_failure BEFORE INSERT ON admin_audit_logs
            FOR EACH ROW EXECUTE FUNCTION reject_correction_audit();""")
    with pytest.raises(DatabaseError):
        record_decision(admin, product, 1, "unresolved", "Corrected evidence", "Inconclusive evidence", expected_head=head)
    assert one("SELECT review_id FROM eligible_training_labels WHERE product_id=%s", [product])["review_id"] == head
    assert one("SELECT count(*) AS n FROM moderation_reviews WHERE product_id=%s", [product])["n"] == 1


@pytest.mark.parametrize("audit_failure", [False, True])
def test_dispute_resolution_requires_evidence_and_commits_audit_atomically(client, case_market, audit_failure):
    from marketplace.services.orders import place_order, transition_order

    buyer, seller, admin = (case_market[key] for key in ("buyer", "seller", "admin"))
    product = case_market["product"]
    order = place_order(buyer, product, 1, uuid4())
    transition_order(seller, order, "accepted", "Accept synthetic order", "placed")
    transition_order(buyer, order, "disputed", "Synthetic delivery dispute", "accepted")
    client.force_login(admin)
    url = f"/admin-app/disputes/{order}/"
    payload = {"expected_status": "disputed", "status": "cancelled", "reason": "Review completed"}
    assert client.post(url, payload).status_code == 409
    assert one("SELECT status FROM transactions WHERE transaction_id=%s", [order])["status"] == "disputed"
    events = one("SELECT count(*) AS n FROM order_status_history WHERE transaction_id=%s", [order])["n"]
    if audit_failure:
        with connection.cursor() as cursor:
            cursor.execute("""CREATE FUNCTION reject_dispute_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Synthetic dispute audit failure'; END $$;
                CREATE TRIGGER dispute_audit_failure BEFORE INSERT ON admin_audit_logs
                FOR EACH ROW EXECUTE FUNCTION reject_dispute_audit();""")
    response = client.post(url, payload | {"evidence": "Reviewed the synthetic delivery evidence"})
    assert response.status_code == (409 if audit_failure else 302)
    assert one("SELECT status FROM transactions WHERE transaction_id=%s", [order])["status"] == ("disputed" if audit_failure else "cancelled")
    assert one("SELECT availability FROM products WHERE product_id=%s", [product])["availability"] == ("reserved" if audit_failure else "available")
    assert one("SELECT count(*) AS n FROM order_status_history WHERE transaction_id=%s", [order])["n"] == events + (0 if audit_failure else 1)
    receipt = one("SELECT audit_id FROM admin_audit_logs WHERE transaction_id=%s", [order])
    assert bool(receipt) is not audit_failure


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


@pytest.mark.django_db(transaction=True, available_apps=[
    "accounts", "marketplace", "risk", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
])
def test_simultaneous_corrections_append_only_one_successor(case_market):
    """Separate committed connections compete for the same canonical head."""
    admin, product = case_market["admin"], case_market["product"]
    record_decision(admin, product, 1, "fraud", "Initial synthetic review", "Synthetic evidence")
    head = one("SELECT review_id FROM eligible_training_labels WHERE product_id=%s", [product])["review_id"]
    barrier = Barrier(2)

    def correct():
        close_old_connections()
        try:
            reviewer = User.objects.get(pk=admin.pk)
            barrier.wait(timeout=10)
            try:
                record_decision(reviewer, product, 1, "unresolved", "Concurrent correction",
                                "Evidence is inconclusive", expected_head=head)
                return "committed"
            except ValidationError:
                return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: correct(), range(2)))
    assert sorted(results) == ["committed", "conflict"]
    assert one("SELECT count(*) AS n FROM moderation_reviews WHERE product_id=%s", [product])["n"] == 2
    assert one("SELECT count(*) AS n FROM moderation_reviews WHERE supersedes_review_id=%s", [head])["n"] == 1
    assert one("SELECT 1 FROM eligible_training_labels WHERE product_id=%s", [product]) is None


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
        assert {"private", "no-store"} <= set(response["Cache-Control"].split(", "))
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
