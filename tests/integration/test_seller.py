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
    assert client.get("/seller-app/").status_code == 200
    assert client.get(f"/seller-app/listings/{product}/draft-images/0/").status_code == 200
    stranger = User.objects.create_user("unrelated@example.invalid", full_name="Other seller")
    stranger.groups.add(Group.objects.get(name="seller"))
    client.force_login(stranger)
    assert client.get(f"/seller-app/listings/{product}/edit/").status_code == 404
    assert client.get(f"/seller-app/listings/{product}/draft-images/0/").status_code == 404


def test_active_order_prevents_draft_and_material_changes(seller, fields):
    product, _ = publish_listing(seller, fields)
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
