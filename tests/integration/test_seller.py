from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.http import Http404

from accounts.models import User
from marketplace.db import actor_transaction, one, rows
from marketplace.services.listings import ListingConflict, publish_listing, save_draft
from tests.unit.test_uploads import image_upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def seller():
    account = User.objects.create_user("seller-test@example.invalid", full_name="Seller test", location="Shanghai")
    account.groups.add(Group.objects.get_or_create(name="seller")[0])
    return account


@pytest.fixture
def fields():
    category = one("SELECT category_id FROM categories ORDER BY category_id LIMIT 1")
    return {"title": "Working desk lamp", "description": "Used desk lamp in good condition.",
            "price": Decimal("12.50"), "original_price": None, "condition": "good", "location": "Shanghai",
            "category_id": category["category_id"]}


def test_partial_draft_is_private_and_publication_queues_atomically(seller, fields, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "public"
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    product, version = save_draft(seller, {"title": "Incomplete"}, [image_upload()])
    assert one("SELECT count(*) AS n FROM product_revisions WHERE product_id=%s", [product])["n"] == 0
    assert one("SELECT count(*) AS n FROM risk_scan_jobs WHERE product_id=%s", [product])["n"] == 0
    _, revision = publish_listing(seller, fields, product_id=product, draft_version=version)
    assert revision == 1
    assert one("SELECT availability,current_revision_no FROM products WHERE product_id=%s", [product]) == {
        "availability": "available", "current_revision_no": 1}
    assert one("SELECT status FROM risk_scan_jobs WHERE product_id=%s", [product])["status"] == "queued"
    assert one("SELECT count(*) AS n FROM product_images WHERE product_id=%s", [product])["n"] == 1
    assert one("SELECT 1 FROM app_listing_drafts WHERE product_id=%s", [product]) is None


def test_revision_and_draft_conflicts_preserve_immutable_content(seller, fields):
    product, version = save_draft(seller, {"title": "First"})
    save_draft(seller, {"title": "Second"}, product_id=product, draft_version=version)
    with pytest.raises(ListingConflict):
        save_draft(seller, {"title": "Stale"}, product_id=product, draft_version=version)
    publish_listing(seller, fields, product_id=product, draft_version=2)
    with pytest.raises(ListingConflict):
        publish_listing(seller, fields, product_id=product)
    publish_listing(seller, fields | {"title": "Revised lamp"}, product_id=product, expected_revision=1)
    assert [row["title"] for row in rows("SELECT title FROM product_revisions WHERE product_id=%s ORDER BY revision_no", [product])] == [
        "Working desk lamp", "Revised lamp"]


def test_cross_owner_and_restricted_account_edits_fail(seller, fields):
    product, _ = publish_listing(seller, fields)
    stranger = User.objects.create_user("stranger-test@example.invalid", full_name="Stranger")
    stranger.groups.add(Group.objects.get(name="seller"))
    with pytest.raises(Http404):
        save_draft(stranger, {"title": "Intrusion"}, product_id=product, expected_revision=1)
    admin = User.objects.create_user("admin-status@example.invalid", full_name="Admin")
    admin.groups.add(Group.objects.get_or_create(name="administrator")[0])
    with actor_transaction(admin, "Restrict synthetic test seller"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [seller.pk])
    with pytest.raises(PermissionDenied):
        publish_listing(seller, fields, product_id=product, expected_revision=1)


def test_private_draft_image_and_page_ownership(client, seller, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    product, _ = save_draft(seller, {"title": "Private"}, [image_upload()])
    client.force_login(seller)
    assert client.get("/sell/").status_code == 200
    assert client.get(f"/sell/listings/{product}/draft-images/0/").status_code == 200
    stranger = User.objects.create_user("unrelated@example.invalid", full_name="Other seller")
    stranger.groups.add(Group.objects.get(name="seller"))
    client.force_login(stranger)
    assert client.get(f"/sell/listings/{product}/edit/").status_code == 404
    assert client.get(f"/sell/listings/{product}/draft-images/0/").status_code == 404


def test_active_order_prevents_draft_and_material_changes(seller, fields, scan_listing):
    product, _ = publish_listing(seller, fields)
    scan_listing(product)
    buyer = User.objects.create_user("buyer-order@example.invalid", full_name="Buyer")
    buyer.groups.add(Group.objects.get_or_create(name="buyer")[0])
    with actor_transaction(buyer, "Purchase synthetic test listing"):
        rows("SELECT place_order(%s,%s,1,%s,%s)", [buyer.pk, product, uuid4(), "a" * 64])
    with pytest.raises(ListingConflict, match="active order"):
        save_draft(seller, {"title": "Attempted material change"}, product_id=product, expected_revision=1)
    with pytest.raises(ListingConflict):
        publish_listing(seller, fields, product_id=product, expected_revision=1)


def test_failed_file_write_rolls_back_revision_and_queue(seller, fields, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("Synthetic storage outage")
    monkeypatch.setattr("marketplace.services.listings.store_image", unavailable)
    before = one("SELECT count(*) AS n FROM products")["n"]
    with pytest.raises(OSError):
        publish_listing(seller, fields, [image_upload()])
    assert one("SELECT count(*) AS n FROM products")["n"] == before


def test_scan_gate_covers_catalog_detail_images_and_direct_purchase(client, seller, fields, settings, tmp_path, scan_listing):
    from django.db import DatabaseError, transaction
    from marketplace.services.orders import place_order
    from django.core.exceptions import ValidationError
    settings.MEDIA_ROOT = tmp_path / "public"
    product, _ = publish_listing(seller, fields, [image_upload(), image_upload()])
    image = one("SELECT storage_key FROM product_images WHERE product_id=%s LIMIT 1", [product])
    image_url = settings.MEDIA_URL + image["storage_key"]
    buyer = User.objects.create_user("scan-buyer@example.invalid", full_name="Buyer")
    buyer.groups.add(Group.objects.get(name="buyer"))
    assert client.get(f"/listings/{product}/").status_code == 404
    assert b"Working desk lamp" not in client.get("/").content
    assert client.get(image_url).status_code == 404
    client.force_login(buyer)
    assert client.get(f"/listings/{product}/reports/new/").status_code == 404
    with pytest.raises(ValidationError, match="assessment"):
        place_order(buyer, product, 1, uuid4())
    with pytest.raises(DatabaseError), transaction.atomic(), actor_transaction(buyer):
        rows("SELECT place_order(%s,%s,1,%s,%s)", [buyer.pk, product, uuid4(), "a" * 64])
    client.force_login(seller)
    assert client.get(image_url).status_code == 200
    assert client.get(f"/listings/{product}/").status_code == 200
    risk = scan_listing(product)
    assert risk["assessment_state"] == "ready"
    client.logout()
    assert client.get(f"/listings/{product}/").status_code == 200
    assert client.get(image_url).status_code == 200
    assert b"Working desk lamp" in client.get("/").content
    # Editing while earlier jobs/results exist cannot reuse their result.
    publish_listing(seller, fields | {"title": "Edited lamp"}, product_id=product, expected_revision=1)
    assert client.get(f"/listings/{product}/").status_code == 404
    assert client.get(image_url).status_code == 404
    assert scan_listing(product)["assessment_state"] == "ready"
    assert client.get(f"/listings/{product}/").status_code == 200
    # Old image URLs remain private even when the replacement revision is public.
    assert client.get(image_url).status_code == 404


def test_failed_scan_and_late_old_completion_never_publish(client, seller, fields, scan_listing):
    product, _ = publish_listing(seller, fields)
    old = one("SELECT * FROM claim_risk_job(interval '2 minutes')")
    assert old["product_id"] == product
    publish_listing(seller, fields | {"title": "Replacement lamp"}, product_id=product, expected_revision=1)
    scan_listing.complete(old)
    assert one("SELECT status FROM risk_scan_jobs WHERE job_id=%s", [old["job_id"]])["status"] == "succeeded"
    assert client.get(f"/listings/{product}/").status_code == 404
    current = one("SELECT * FROM claim_risk_job(interval '2 minutes')")
    rows("SELECT fail_risk_job(%s,%s,'invalid_model_or_features',false)", [current["job_id"], current["claim_token"]])
    risk = one("SELECT * FROM current_listing_risk WHERE product_id=%s", [product])
    assert risk["assessment_state"] == "failed" and risk["risk_score"] is None
    assert client.get(f"/listings/{product}/").status_code == 404
    publish_listing(seller, fields, product_id=product, expected_revision=2)
    assert scan_listing(product)["assessment_state"] == "ready"


def test_unavailable_model_keeps_submission_pending(client, seller, fields):
    product, _ = publish_listing(seller, fields)
    assert one("SELECT * FROM claim_risk_job(interval '2 minutes')") is None
    risk = one("SELECT * FROM current_listing_risk WHERE product_id=%s", [product])
    assert risk["assessment_state"] == "pending" and risk["risk_score"] is None
    assert client.get(f"/listings/{product}/").status_code == 404
    client.force_login(seller)
    assert b"compatible active model" in client.get(f"/sell/listings/{product}/revisions/").content


def test_seller_order_ownership_transitions_snapshots_and_pending_mapping(client, seller, fields, scan_listing):
    from django.db import DatabaseError, transaction
    from marketplace.services.orders import place_order, transition_order
    from django.core.exceptions import ValidationError
    product, _ = publish_listing(seller, fields)
    scan_listing(product)
    buyer = User.objects.create_user("workflow-buyer@example.invalid", full_name="Buyer")
    buyer.groups.add(Group.objects.get(name="buyer"))
    stranger = User.objects.create_user("workflow-stranger@example.invalid", full_name="Other seller")
    stranger.groups.add(Group.objects.get(name="seller"))
    order = place_order(buyer, product, 1, uuid4(), acknowledge=True)
    with pytest.raises(DatabaseError), transaction.atomic():
        place_order(buyer, product, 1, uuid4(), acknowledge=True)
    with pytest.raises(PermissionDenied):
        transition_order(stranger, order, "accepted", "Intrusion", "placed")
    client.force_login(stranger)
    assert client.get(f"/sell/orders/{order}/").status_code == 404
    client.force_login(seller)
    assert b"Pending" in client.get(f"/sell/orders/{order}/").content
    assert str(order).encode() in client.get("/sell/sales/?status=pending").content
    with pytest.raises(DatabaseError), transaction.atomic():
        transition_order(buyer, order, "accepted", "Wrong actor", "placed")
    transition_order(seller, order, "accepted", "Accepted", "placed")
    with pytest.raises(ValidationError):
        transition_order(seller, order, "shipped", "Stale", "placed")
    transition_order(seller, order, "shipped", "Dispatched", "accepted")
    with pytest.raises(DatabaseError), transaction.atomic():
        transition_order(seller, order, "completed", "Wrong actor", "shipped")
    transition_order(buyer, order, "completed", "Received", "shipped")
    snapshot = one("SELECT * FROM seller_order_history WHERE transaction_id=%s", [order])
    assert snapshot["ordered_title"] == fields["title"] and snapshot["agreed_price"] == fields["price"]
    with pytest.raises(ListingConflict):
        publish_listing(seller, fields, product_id=product, expected_revision=1)
    assert one("SELECT count(*) AS n FROM order_status_history WHERE transaction_id=%s", [order])["n"] == 4



def test_configuration_change_makes_previously_public_result_stale(client, seller, fields, scan_listing):
    product, _ = publish_listing(seller, fields)
    assert scan_listing(product)["assessment_state"] == "ready"
    assert client.get(f"/listings/{product}/").status_code == 200
    admin = User.objects.filter(groups__name="administrator").first()
    model = one("SELECT * FROM risk_models WHERE state='active'")
    with actor_transaction(admin, "Verify stale publication after rules change"):
        rules = one("INSERT INTO risk_rulesets(version,feature_schema_id,created_by) VALUES('new-publication-rules',%s,%s) RETURNING ruleset_id",
                    [model["feature_schema_id"], admin.pk])["ruleset_id"]
        rows("INSERT INTO risk_rules(ruleset_id,rule_key,numeric_value,description) VALUES(%s,'medium_min',40,'Test threshold'),(%s,'high_min',75,'Test threshold')", [rules, rules])
        rows("SELECT activate_risk_configuration(%s,%s)", [model["model_id"], rules])
    risk = one("SELECT * FROM current_listing_risk WHERE product_id=%s", [product])
    assert risk["assessment_state"] == "stale" and risk["risk_score"] is None
    assert client.get(f"/listings/{product}/").status_code == 404
    assert b"Working desk lamp" not in client.get("/").content



def test_withdrawal_archives_after_cancellation_and_preserves_purchased_snapshot(client, seller, fields, scan_listing):
    from marketplace.services.listings import withdraw_listing
    from marketplace.services.orders import place_order, transition_order
    product, _ = publish_listing(seller, fields)
    scan_listing(product)
    buyer = User.objects.create_user("archive-buyer@example.invalid", full_name="Buyer")
    buyer.groups.add(Group.objects.get(name="buyer"))
    order = place_order(buyer, product, 1, uuid4(), acknowledge=True)
    with pytest.raises(ListingConflict):
        withdraw_listing(seller, product)
    transition_order(seller, order, "cancelled", "Item unavailable for fulfilment", "placed")
    assert one("SELECT availability FROM products WHERE product_id=%s", [product])["availability"] == "available"
    stranger = User.objects.create_user("archive-stranger@example.invalid", full_name="Other seller")
    stranger.groups.add(Group.objects.get(name="seller"))
    with pytest.raises(Http404):
        withdraw_listing(stranger, product)
    withdraw_listing(seller, product)
    assert one("SELECT visibility FROM products WHERE product_id=%s", [product])["visibility"] == "removed_by_seller"
    assert one("SELECT ordered_title FROM seller_order_history WHERE transaction_id=%s", [order])["ordered_title"] == fields["title"]
    assert client.get(f"/listings/{product}/").status_code == 404
    client.force_login(buyer)
    assert client.get(f"/listings/{product}/revisions/1/").status_code == 200
    assert one("SELECT count(*) AS n FROM product_revisions WHERE product_id=%s", [product])["n"] == 1
