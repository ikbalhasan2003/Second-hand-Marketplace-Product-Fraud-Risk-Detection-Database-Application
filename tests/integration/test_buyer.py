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
def market(scan_listing):
    result = {}
    for role, key in [("seller", "seller"), ("buyer", "buyer"), ("buyer", "stranger"), ("administrator", "admin")]:
        user = User.objects.create_user(f"{key}-buyer-test@example.invalid", full_name=key.title(), location="Shanghai")
        user.groups.add(Group.objects.get(name=role))
        result[key] = user
    fields = {"title": "Working telescope", "description": "Used telescope for observing the moon.", "category_id": one("SELECT category_id FROM categories LIMIT 1")["category_id"], "price": Decimal("80.00"), "condition": "good", "location": "Shanghai"}
    result["product"], result["revision"] = publish_listing(result["seller"], fields)
    scan_listing(result["product"])
    return result


def test_public_search_and_low_filter_never_invent_score(client, market):
    page = client.get("/listings/", {"q": "telescope"})
    assert page.status_code == 200
    assert b"Working telescope" in page.content
    low = client.get("/listings/", {"risk": "low"})
    risk = one("SELECT * FROM current_listing_risk WHERE product_id=%s", [market["product"]])
    assert (b"Working telescope" in low.content) == (risk["risk_level"] == "low")
    invalid = client.get("/listings/", {"minimum": "100", "maximum": "10"})
    assert b"Minimum price must not exceed" in invalid.content


def test_purchase_idempotency_ownership_and_historical_terms(client, market):
    client.force_login(market["buyer"])
    payload = {"revision_no": 1, "request_key": str(uuid4())}
    endpoint = f"/listings/{market['product']}/orders/"
    first = client.post(endpoint, payload)
    second = client.post(endpoint, payload)
    assert first.status_code == 302 and second.url == first.url
    assert one("SELECT count(*) AS n FROM transactions WHERE product_id=%s", [market["product"]])["n"] == 1
    snapshot = one("SELECT assessment_snapshot FROM transactions WHERE product_id=%s", [market["product"]])["assessment_snapshot"]
    assert snapshot["revision_no"] == 1 and snapshot["assessment_state"] == "ready"
    assert snapshot["risk_id"] is not None and "observed_factors" in snapshot["evidence"]
    from django.db import DatabaseError
    with pytest.raises(DatabaseError), actor_transaction(market["buyer"]):
        rows("UPDATE transactions SET assessment_snapshot=NULL WHERE product_id=%s", [market["product"]])
    assert client.get(first.url).status_code == 200
    client.force_login(market["stranger"])
    assert client.get(first.url).status_code == 404
    assert client.get(f"/listings/{market['product']}/revisions/1/").status_code == 404
    assert client.post(endpoint, {"revision_no": 1, "request_key": str(uuid4())}).status_code == 409


def test_chat_participants_and_recipient_only_read(client, market):
    client.force_login(market["buyer"])
    start = client.post(f"/listings/{market['product']}/conversations/")
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
    seller_url = url.replace("/conversations/", "/sell/conversations/").replace("/orders/", "/sell/orders/")
    assert client.get(seller_url + "messages/").json()["messages"][0]["message_text"].startswith("<script>")
    assert client.post(seller_url + "read/", {"through_id": message["message_id"]}).status_code == 200
    assert one("SELECT read_at FROM chat_messages WHERE message_id=%s", [message["message_id"]])["read_at"] is not None


def test_chat_rejects_out_of_range_message_ids(client, market):
    client.force_login(market["buyer"])
    url = client.post(f"/listings/{market['product']}/conversations/").url
    too_large = str(2**63)
    for cursor in ("after_id", "before_id"):
        assert client.get(url + "messages/", {cursor: too_large}).status_code == 400
    assert client.post(url + "read/", {"through_id": too_large}).status_code == 400
    assert client.post(url + "read/", {"message_ids": too_large}).status_code == 400


def test_blocked_order_obligations_and_removed_visibility(client, market):
    order = place_order(market["buyer"], market["product"], 1, uuid4())
    with actor_transaction(market["admin"], "Synthetic restriction with existing agreement"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [market["buyer"].pk])
        rows("UPDATE products SET visibility='removed_by_admin' WHERE product_id=%s", [market["product"]])
    client.force_login(market["buyer"])
    assert client.get(f"/orders/{order}/").status_code == 200
    response = client.post(f"/orders/{order}/", {"expected_status": "placed", "status": "cancelled", "reason": "Cannot fulfil agreement"})
    assert response.status_code == 302
    assert one("SELECT visibility FROM products WHERE product_id=%s", [market["product"]])["visibility"] == "removed_by_admin"


def test_unscanned_replacement_cannot_be_accessed_via_report_form(client, market):
    fields = {"title": "Revised telescope", "description": "Updated condition notes", "category_id": one("SELECT category_id FROM categories LIMIT 1")["category_id"], "price": 85, "condition": "good", "location": "Shanghai"}
    publish_listing(market["seller"], fields, product_id=market["product"], expected_revision=1)
    client.force_login(market["buyer"])
    response = client.post(f"/listings/{market['product']}/reports/", {"revision_no": 1, "reason_code": "other", "comment": "Please review my concern"})
    assert response.status_code == 404
    assert b"Revised telescope" not in response.content
    assert one("SELECT count(*) AS n FROM fraud_reports")["n"] == 0


@pytest.mark.parametrize("filters", [
    {"minimum": "-1"}, {"maximum": "NaN"}, {"minimum": "1.001"},
    {"maximum": "999999999999999999999999"}, {"category": "invalid"}, {"condition": "invalid"},
])
def test_invalid_filters_return_form_errors(client, market, filters):
    response = client.get("/listings/", filters)
    assert response.status_code == 200
    assert response.context["form"].errors
    assert response.context["count"] == 0


def test_combined_filters_and_pagination_preserve_selection(client, market):
    category = one("SELECT category_id FROM product_revisions WHERE product_id=%s", [market["product"]])["category_id"]
    filters = {"q": "telescope", "category": str(category), "minimum": "80", "maximum": "80",
               "location": "shanghai", "condition": "good", "sort": "price", "page": "999"}
    response = client.get("/listings/", filters)
    assert response.context["count"] == 1
    assert response.context["page"].number == 1
    assert "condition=good" in response.context["query"]
    assert "page=" not in response.context["query"]
    assert response.context["form"]["location"].value() == "shanghai"


def test_catalog_second_page_retains_filters(client, market, scan_listing):
    category = one("SELECT category_id FROM categories LIMIT 1")["category_id"]
    for number in range(12):
        publish_listing(market["seller"], {"title": f"Pagination telescope {number}",
            "description": "Synthetic browsing pagination fixture", "category_id": category,
            "price": 80, "condition": "good", "location": "Shanghai"})
    scan_listing(market["product"])
    response = client.get("/listings/", {"q": "telescope", "condition": "good", "minimum": "80", "page": "2"})
    assert response.context["count"] == 13
    assert response.context["page"].number == 2
    assert len(response.context["listings"]) == 1
    assert "condition=good" in response.context["query"]
    assert "minimum=80" in response.context["query"]


def test_profile_validation_and_privilege_fields_are_ignored(client, market):
    user = market["buyer"]
    client.force_login(user)
    payload = {"action": "profile", "profile-full_name": "Updated Buyer", "profile-location": "Beijing",
               "profile-private_contact": "private@example.invalid", "user_id": market["seller"].pk,
               "status": "blocked", "is_superuser": "true", "email": "changed@example.invalid"}
    assert client.post("/account/", payload).status_code == 302
    user.refresh_from_db()
    assert user.full_name == "Updated Buyer"
    assert user.private_contact == "private@example.invalid"
    assert user.status == "active" and not user.is_superuser
    assert user.email == "buyer-buyer-test@example.invalid"
    assert client.get("/account/")["Cache-Control"] == "private, no-store"
    assert client.post("/account/", payload | {"profile-private_contact": "invalid"}).status_code == 200
    user.refresh_from_db()
    assert user.private_contact == "private@example.invalid"
    assert b"private@example.invalid" not in client.get(f"/listings/{market['product']}/").content
    assert client.get("/admin-app/").status_code == 403


def test_seller_profile_preserves_required_contact_and_public_privacy(client, market):
    client.force_login(market["seller"])
    payload = {"action": "profile", "profile-full_name": "Public shop name",
               "profile-location": "Shanghai", "profile-private_contact": "private-shop@example.invalid"}
    assert client.post("/account/", payload).status_code == 302
    assert client.post("/account/", payload | {"profile-private_contact": ""}).context["profile_form"].errors
    client.logout()
    response = client.get(f"/listings/{market['product']}/")
    assert response.status_code == 200
    assert b"Public shop name" in response.content
    assert b"private-shop@example.invalid" not in response.content


def test_seller_location_change_invalidates_assessment_and_queues_scan(client, market):
    client.force_login(market["seller"])
    assert client.post("/account/", {"action": "profile", "profile-full_name": "Seller",
        "profile-location": "Beijing", "profile-private_contact": "seller-private@example.invalid"}).status_code == 302
    risk = one("SELECT * FROM current_listing_risk WHERE product_id=%s", [market["product"]])
    assert risk["assessment_state"] != "ready"
    assert one("SELECT 1 FROM risk_scan_jobs WHERE product_id=%s AND context_version=%s AND status='queued'",
               [market["product"], risk["context_version"]])


def test_blocked_moderator_cannot_read_private_listing_revision(client, market):
    user = market["admin"]
    operator = User.objects.filter(groups__name="administrator").exclude(pk=user.pk).first()
    with actor_transaction(operator, "Restrict synthetic moderator"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [user.pk])
    client.force_login(user)
    assert client.get(f"/listings/{market['product']}/revisions/1/").status_code == 404


# Scoped teardown enables CASCADE for SQL-owned unmanaged domain tables that
# reference users; Django's default flush cannot discover those tables.
@pytest.mark.django_db(transaction=True, available_apps=[
    "accounts", "marketplace", "risk", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
])
def test_concurrent_buyers_cannot_double_purchase(market):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, DatabaseError
    from django.core.exceptions import ValidationError
    barrier = Barrier(2)

    def purchase(user):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                return place_order(user, market["product"], 1, uuid4())
            except (DatabaseError, ValidationError):
                return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(purchase, [market["buyer"], market["stranger"]]))
    assert sum(result is not None for result in results) == 1
    order = one("SELECT revision_no,assessment_snapshot FROM transactions WHERE product_id=%s", [market["product"]])
    assert order["revision_no"] == 1 and order["assessment_snapshot"]["risk_id"] is not None
    assert one("SELECT count(*) AS n FROM transactions WHERE product_id=%s", [market["product"]])["n"] == 1
