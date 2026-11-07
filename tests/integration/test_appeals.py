import io
import pytest
from PIL import Image
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from marketplace.db import actor_transaction, one, rows
from marketplace.services.appeals import submit_appeal, decide_appeal
from tests.integration.test_accounts import member, PASSWORD

pytestmark = pytest.mark.django_db


def blocked(role="seller"):
    user = member("appeal-owner@example.invalid", role)
    admin = member("appeal-admin@example.invalid", "administrator")
    with actor_transaction(admin, "Test block"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [user.pk])
    return user, admin


def test_appeal_login_evidence_privacy_and_approval(client, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    user, admin = blocked()
    assert client.post("/login/", {"email": user.email, "password": PASSWORD}).url == "/account/appeals/"
    assert client.get("/account/appeals/").status_code == 200
    image = io.BytesIO()
    Image.new("RGB", (4, 4)).save(image, format="PNG")
    response = client.post("/account/appeals/", {"reason": "Please review my account restriction", "evidence": SimpleUploadedFile("proof.png", image.getvalue())})
    assert response.status_code == 302
    appeal = one("SELECT * FROM account_appeals WHERE user_id=%s", [user.pk])
    evidence = one("SELECT * FROM account_appeal_evidence WHERE appeal_id=%s", [appeal["appeal_id"]])
    url = f"/account/appeals/evidence/{evidence['evidence_id']}/"
    assert client.get(url).status_code == 200
    assert client.get("/listing-media/" + evidence["storage_key"]).status_code == 404
    with pytest.raises(ValidationError):
        submit_appeal(user, "Duplicate appeal reason")
    other = member("other-appeal@example.invalid")
    client.force_login(other)
    assert client.get(url).status_code == 403
    assert client.get("/admin-app/appeals/").status_code == 403
    client.force_login(admin)
    assert client.get(url).status_code == 200
    assert client.get("/admin-app/appeals/").status_code == 200
    decide_appeal(admin, appeal["appeal_id"], "reviewing", "Reviewing submitted evidence", "pending")
    decide_appeal(admin, appeal["appeal_id"], "approved", "Evidence supports restoring account", "reviewing")
    user.refresh_from_db()
    assert user.status == "active"
    result = one("SELECT * FROM account_appeals WHERE appeal_id=%s", [appeal["appeal_id"]])
    assert result["reviewer_id"] == admin.pk and result["reviewed_at"]
    assert one("SELECT count(*) AS n FROM admin_audit_logs WHERE user_id=%s AND action_type='account_appeal_decision'", [user.pk])["n"] == 2
    with pytest.raises(ValidationError):
        decide_appeal(admin, appeal["appeal_id"], "rejected", "Stale request", "reviewing")


def test_rejection_and_validation(client, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    user, admin = blocked("buyer")
    with pytest.raises(ValidationError):
        submit_appeal(user, "short")
    with pytest.raises(ValidationError):
        submit_appeal(user, "Reason for appeal", [SimpleUploadedFile("bad.png", b"invalid")])
    assert not one("SELECT 1 FROM account_appeals WHERE user_id=%s", [user.pk])
    appeal_id = submit_appeal(user, "Please reconsider restriction")
    with pytest.raises(PermissionDenied):
        decide_appeal(user, appeal_id, "approved", "Own decision", "pending")
    decide_appeal(admin, appeal_id, "rejected", "Insufficient supporting information", "pending")
    user.refresh_from_db()
    assert user.status == "blocked"
    assert submit_appeal(user, "Additional information for reconsideration") != appeal_id
    client.force_login(user)
    assert client.post("/account/enable/seller/").status_code == 403
    assert client.get("/orders/").status_code == 200


def test_audit_failure_rolls_back_decision_and_unblock(monkeypatch):
    import marketplace.services.appeals as service
    user, admin = blocked()
    appeal_id = submit_appeal(user, "Please review restriction")
    original = service.rows

    def fail_after_update(sql, params=()):
        result = original(sql, params)
        if sql.startswith("UPDATE account_appeals"):
            raise RuntimeError("Simulated transaction failure")
        return result

    monkeypatch.setattr(service, "rows", fail_after_update)
    with pytest.raises(RuntimeError):
        decide_appeal(admin, appeal_id, "approved", "Restore account", "pending")
    user.refresh_from_db()
    assert user.status == "blocked"
    assert one("SELECT status FROM account_appeals WHERE appeal_id=%s", [appeal_id])["status"] == "pending"
    assert not one("SELECT 1 FROM admin_audit_logs WHERE action_type='account_appeal_decision' AND user_id=%s", [user.pk])


def test_restricted_web_role_can_submit_and_review(settings, tmp_path):
    from django.db import connection
    from pathlib import Path
    from tests.integration.test_admin import apply_grants
    user, admin = blocked()
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    apply_grants(Path(__file__).resolve().parents[2])
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE secondhand_web")
    try:
        appeal_id = submit_appeal(user, "Please reconsider my restriction")
        decide_appeal(admin, appeal_id, "approved", "Reviewed evidence and restored account", "pending")
        assert one("SELECT status FROM users WHERE user_id=%s", [user.pk])["status"] == "active"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


def test_database_rejects_owner_self_approval_and_terminal_edits():
    from django.db import DatabaseError, transaction
    user, admin = blocked()
    appeal_id = submit_appeal(user, "Please reconsider restriction")
    with pytest.raises(DatabaseError), transaction.atomic(), actor_transaction(user, "Attempt self approval"):
        rows("UPDATE account_appeals SET status='approved',decision_notes='Self approval' WHERE appeal_id=%s", [appeal_id])
    decide_appeal(admin, appeal_id, "rejected", "No grounds to restore access", "pending")
    with pytest.raises(DatabaseError), transaction.atomic(), actor_transaction(admin, "Attempt rewrite"):
        rows("UPDATE account_appeals SET decision_notes='Changed history' WHERE appeal_id=%s", [appeal_id])
