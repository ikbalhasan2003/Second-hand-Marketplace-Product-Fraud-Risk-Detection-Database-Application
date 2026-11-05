"""One continuous, three-session AC-23 HTTP acceptance scenario."""
import io
from uuid import uuid4

import pytest
from PIL import Image
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.models import User
from marketplace.db import one


@pytest.mark.django_db
def test_cross_application_publish_chat_fulfil_report_review(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "public"
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    clients = {}
    for role in ("buyer", "seller", "administrator"):
        user = User.objects.create_user(f"delivery-{role}@example.invalid", full_name=f"Synthetic {role}")
        user.groups.add(Group.objects.get(name=role))
        clients[role] = Client()
        clients[role].force_login(user)
    buyer, seller, admin = (clients[role] for role in ("buyer", "seller", "administrator"))
    published = seller.post("/seller-app/listings/new/", {
        "action": "publish", "expected_revision": 0, "draft_version": 0,
        "title": "Synthetic delivery telescope", "description": "Synthetic course acceptance scenario.",
        "category_id": one("SELECT category_id FROM categories WHERE is_active LIMIT 1")["category_id"],
        "condition": "good", "price": "80.00", "location": "Shanghai",
    })
    assert published.status_code == 302
    product = one("SELECT product_id FROM products WHERE current_revision_no=1")["product_id"]
    listing_url = f"/buyer-app/listings/{product}/"
    detail = buyer.get(listing_url)
    assert detail.context["listing"]["assessment_state"] == "pending"
    assert b"Synthetic delivery telescope" in buyer.get("/buyer-app/listings/").content
    assert b"Scan pending" in seller.get("/seller-app/").content
    conversation = buyer.post(listing_url + "conversations/").url
    assert buyer.post(conversation, {"message": "Can you confirm the recorded condition?"}).status_code == 302
    seller_thread = conversation.replace("buyer-app", "seller-app")
    assert b"recorded condition" in seller.get(seller_thread).content
    assert seller.post(seller_thread, {"message": "The description records the current condition."}).status_code == 302
    assert b"current condition" in buyer.get(conversation).content
    ordered = buyer.post(listing_url + "orders/", {
        "revision_no": 1, "request_key": str(uuid4()), "review_token": detail.context["review_token"],
    })
    assert ordered.status_code == 302
    order_url = ordered.url
    seller_order = order_url.replace("buyer-app", "seller-app")
    for client, url, previous, following in (
        (seller, seller_order, "placed", "accepted"),
        (seller, seller_order, "accepted", "shipped"),
        (buyer, order_url, "shipped", "completed"),
    ):
        assert client.post(url, {"expected_status": previous, "status": following, "reason": "Synthetic fulfilment acceptance step"}).status_code == 302
        assert buyer.get(order_url).context["order"]["status"] == following
        assert seller.get(seller_order).context["order"]["status"] == following
    order = buyer.get(order_url).context["order"]
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(image, "PNG")
    reported = buyer.post(listing_url + "reports/", {
        "revision_no": 1, "order_id": order["transaction_id"], "reason_code": "other",
        "comment": "Synthetic concern for human review", "evidence": SimpleUploadedFile("evidence.png", image.getvalue(), "image/png"),
    })
    assert reported.status_code == 302
    report = buyer.get(reported.url).context["report"]
    attachment = one("SELECT attachment_id FROM report_attachments WHERE report_id=%s", [report["report_id"]])["attachment_id"]
    assert seller.get(f"/buyer-app/evidence/{attachment}/").status_code == 404
    assert admin.get(f"/buyer-app/evidence/{attachment}/").status_code == 200
    case_url = f"/admin-app/cases/{product}/"
    assert b"Synthetic concern" in admin.get(case_url).content
    reviewed = admin.post(case_url, {"operation": "decision", "revision_no": 1, "report_id": report["report_id"], "verdict": "unresolved", "reason": "Synthetic evidence remains inconclusive", "evidence": "Reviewed the immutable revision and private image."})
    assert reviewed.status_code == 302 and "/audit-log/" in reviewed.url
    assert admin.get(reviewed.url).status_code == 200
    resolved = admin.post(case_url, {"operation": "moderate", "report_id": report["report_id"], "action": "resolved", "expected": "pending", "reason": "Synthetic review completed without a fraud finding", "outcome": "Review complete; available evidence is inconclusive."})
    assert resolved.status_code == 302
    assert b"available evidence is inconclusive" in buyer.get(reported.url).content
    assert one("SELECT availability,visibility FROM products WHERE product_id=%s", [product]) == {"availability": "sold", "visibility": "visible"}
