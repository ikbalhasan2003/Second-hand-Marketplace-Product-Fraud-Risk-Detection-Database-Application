from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group

from accounts.models import User
from marketplace.db import actor_transaction, one, rows
from marketplace.services.listings import publish_listing
from tests.unit.test_uploads import image_upload

pytestmark = pytest.mark.django_db


def member(email, role):
    account = User.objects.create_user(email, full_name=role.title())
    account.groups.add(Group.objects.get_or_create(name=role)[0])
    return account


@pytest.fixture
def case(client, settings, tmp_path, scan_listing):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    settings.MEDIA_ROOT = tmp_path / "public"
    seller = member("case-seller@example.invalid", "seller")
    buyer = member("case-buyer@example.invalid", "buyer")
    category = one("SELECT category_id FROM categories ORDER BY category_id LIMIT 1")["category_id"]
    fields = {"title": "Case target", "description": "A synthetic listing for privacy checks.", "category_id": category,
              "condition": "good", "price": Decimal("35.00"), "original_price": None, "location": "Shanghai"}
    product, _ = publish_listing(seller, fields)
    scan_listing(product)
    client.force_login(buyer)
    response = client.post(f"/listings/{product}/reports/", {
        "revision_no": 1, "reason_code": "other", "comment": "Please review this synthetic concern."})
    assert response.status_code == 302
    report = one("SELECT * FROM fraud_reports WHERE product_id=%s", [product])
    return seller, buyer, product, report["report_id"], fields


def test_blocked_reporter_can_append_private_existing_case_evidence(client, case):
    seller, buyer, product, report_id, _ = case
    admin = member("case-admin@example.invalid", "administrator")
    with actor_transaction(admin, "Restrict synthetic reporter"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [buyer.pk])
    client.force_login(buyer)
    response = client.post(f"/reports/{report_id}/evidence/", {"evidence": image_upload()})
    assert response.status_code == 302
    attachment = one("SELECT attachment_id FROM report_attachments WHERE report_id=%s", [report_id])
    assert client.get(f"/evidence/{attachment['attachment_id']}/").status_code == 200
    assert client.post(f"/listings/{product}/reports/", {
        "revision_no": 1, "reason_code": "other", "comment": "New report forbidden"}).status_code == 403
    client.force_login(seller)
    assert client.get(f"/evidence/{attachment['attachment_id']}/").status_code == 404
    stranger = member("case-stranger@example.invalid", "buyer")
    client.force_login(stranger)
    assert client.post(f"/reports/{report_id}/evidence/", {"evidence": image_upload()}).status_code == 404


def test_evidence_limit_is_case_total_and_storage_failure_rolls_back(client, case, monkeypatch):
    _, buyer, _, report_id, _ = case
    client.force_login(buyer)
    assert client.post(f"/reports/{report_id}/evidence/", {
        "evidence": [image_upload(), image_upload(), image_upload()]}).status_code == 302
    assert client.post(f"/reports/{report_id}/evidence/", {"evidence": image_upload()}).status_code == 409
    assert one("SELECT count(*) AS n FROM report_attachments WHERE report_id=%s", [report_id])["n"] == 3
    def unavailable(*args, **kwargs):
        raise OSError("Synthetic storage failure")
    monkeypatch.setattr("marketplace.uploads.store_image", unavailable)
    # A different report has no attachments, so failure exercises storage rollback rather than the limit.
    with actor_transaction(buyer):
        extra = one("""INSERT INTO fraud_reports(product_id,revision_no,reporter_id,reason_code,comment)
            SELECT product_id,revision_no,reporter_id,'other','Second synthetic concern' FROM fraud_reports
            WHERE report_id=%s RETURNING report_id""", [report_id])["report_id"]
    assert client.post(f"/reports/{extra}/evidence/", {"evidence": image_upload()}).status_code == 409
    assert one("SELECT count(*) AS n FROM report_attachments WHERE report_id=%s", [extra])["n"] == 0


def test_order_linked_report_displays_purchased_snapshot(client, case):
    seller, buyer, product, _, fields = case
    with actor_transaction(buyer, "Create synthetic order"):
        order = one("SELECT place_order(%s,%s,1,%s,%s) AS id", [buyer.pk, product, uuid4(), "b" * 64])["id"]
        rows("SELECT transition_order(%s,'cancelled')", [order])
    publish_listing(seller, fields | {"title": "A later title"}, product_id=product, expected_revision=1)
    client.force_login(buyer)
    response = client.get(f"/listings/{product}/reports/new/?order={order}")
    assert response.status_code == 200
    assert response.context["listing"]["revision_no"] == 1
    assert response.context["listing"]["title"] == "Case target"
    assert client.get(f"/listings/{product}/reports/new/?order=invalid").status_code == 404



def test_initial_report_rejects_disguised_image_without_partial_case(client, case):
    from django.core.files.uploadedfile import SimpleUploadedFile
    _, buyer, product, _, _ = case
    client.force_login(buyer)
    before = one("SELECT count(*) AS n FROM fraud_reports")["n"]
    response = client.post(f"/listings/{product}/reports/", {
        "revision_no": 1, "reason_code": "other", "comment": "Please inspect this concern",
        "evidence": SimpleUploadedFile("screenshot.png", b"not an image", "image/png"),
    })
    assert response.status_code == 409
    assert one("SELECT count(*) AS n FROM fraud_reports")["n"] == before
    assert one("SELECT count(*) AS n FROM report_attachments")["n"] == 0
