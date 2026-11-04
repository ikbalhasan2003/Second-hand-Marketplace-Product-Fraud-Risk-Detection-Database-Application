from uuid import uuid4
from decimal import Decimal
import pytest
from django.contrib.auth.models import Group
from accounts.models import User
from marketplace.db import actor_transaction, one, rows
from marketplace.services.listings import publish_listing
from marketplace.services.orders import place_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def market():
    result = {}
    for role, key in [("seller", "seller"), ("buyer", "buyer"), ("buyer", "stranger"), ("administrator", "admin")]:
        user = User.objects.create_user(f"{key}-buyer-test@example.invalid", full_name=key.title(), location="Shanghai")
        user.groups.add(Group.objects.get(name=role))
        result[key] = user
    fields = {"title": "Working telescope", "description": "Used telescope for observing the moon.", "category_id": one("SELECT category_id FROM categories LIMIT 1")["category_id"], "price": Decimal("80.00"), "condition": "good", "location": "Shanghai"}
    result["product"], result["revision"] = publish_listing(result["seller"], fields)
    return result


def test_public_search_and_low_filter_never_invent_score(client, market):
    page = client.get("/buyer-app/listings/", {"q": "telescope"})
    assert page.status_code == 200
    assert b"Working telescope" in page.content
    low = client.get("/buyer-app/listings/", {"risk": "low"})
    assert b"Working telescope" not in low.content
    invalid = client.get("/buyer-app/listings/", {"minimum": "100", "maximum": "10"})
    assert b"Minimum price must not exceed" in invalid.content


def test_purchase_idempotency_ownership_and_historical_terms(client, market):
    client.force_login(market["buyer"])
    payload = {"revision_no": 1, "request_key": str(uuid4())}
    endpoint = f"/buyer-app/listings/{market['product']}/orders/"
    first = client.post(endpoint, payload)
    second = client.post(endpoint, payload)
    assert first.status_code == 302 and second.url == first.url
    assert one("SELECT count(*) AS n FROM transactions WHERE product_id=%s", [market["product"]])["n"] == 1
    assert client.get(first.url).status_code == 200
    client.force_login(market["stranger"])
    assert client.get(first.url).status_code == 404
    assert client.get(f"/buyer-app/listings/{market['product']}/revisions/1/").status_code == 404
    assert client.post(endpoint, {"revision_no": 1, "request_key": str(uuid4())}).status_code == 409


def test_chat_participants_and_recipient_only_read(client, market):
    client.force_login(market["buyer"])
    start = client.post(f"/buyer-app/listings/{market['product']}/conversations/")
    assert start.status_code == 302
    url = start.url
    assert client.post(url, {"message": "<script>alert(1)</script>"}).status_code == 302
    message = one("SELECT * FROM chat_messages LIMIT 1")
    assert client.post(url + "read/", {"through_id": message["message_id"]}).status_code == 200
    assert one("SELECT read_at FROM chat_messages WHERE message_id=%s", [message["message_id"]])["read_at"] is None
    client.force_login(market["stranger"])
    assert client.get(url + "messages/").status_code == 404
    assert client.post(url + "read/", {"through_id": message["message_id"]}).status_code == 404
    client.force_login(market["seller"])
    seller_url = url.replace("buyer-app", "seller-app")
    assert client.get(seller_url + "messages/").json()["messages"][0]["message_text"].startswith("<script>")
    assert client.post(seller_url + "read/", {"through_id": message["message_id"]}).status_code == 200
    assert one("SELECT read_at FROM chat_messages WHERE message_id=%s", [message["message_id"]])["read_at"] is not None


def test_blocked_order_obligations_and_removed_visibility(client, market):
    order = place_order(market["buyer"], market["product"], 1, uuid4())
    with actor_transaction(market["admin"], "Synthetic restriction with existing agreement"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [market["buyer"].pk])
        rows("UPDATE products SET visibility='removed_by_admin' WHERE product_id=%s", [market["product"]])
    client.force_login(market["buyer"])
    assert client.get(f"/buyer-app/orders/{order}/").status_code == 200
    response = client.post(f"/buyer-app/orders/{order}/", {"expected_status": "placed", "status": "cancelled", "reason": "Cannot fulfil agreement"})
    assert response.status_code == 302
    assert one("SELECT visibility FROM products WHERE product_id=%s", [market["product"]])["visibility"] == "removed_by_admin"


def test_stale_report_revision_returns_conflict_and_preserves_input(client, market):
    fields = {"title": "Revised telescope", "description": "Updated condition notes", "category_id": one("SELECT category_id FROM categories LIMIT 1")["category_id"], "price": 85, "condition": "good", "location": "Shanghai"}
    publish_listing(market["seller"], fields, product_id=market["product"], expected_revision=1)
    client.force_login(market["buyer"])
    response = client.post(f"/buyer-app/listings/{market['product']}/reports/", {"revision_no": 1, "reason_code": "other", "comment": "Please review my concern"})
    assert response.status_code == 409
    assert b"Please review my concern" in response.content
    assert one("SELECT count(*) AS n FROM fraud_reports")["n"] == 0
