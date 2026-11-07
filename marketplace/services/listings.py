"""Owner-scoped drafts and immutable scan submissions; public release requires a current result."""
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404

from marketplace.db import actor_transaction, one, rows
from marketplace.uploads import copy_stored_image, remove_stored, store_image, validate_image
from ml.contract import text_fingerprint

FIELDS = {"title": 200, "description": 20000, "category_id": 32, "condition": 32,
          "price": 32, "original_price": 32, "location": 150}


class ListingConflict(Exception):
    pass


def _editable(user, product_id, expected_revision, draft_version):
    product = one("SELECT * FROM products WHERE product_id=%s FOR UPDATE", [product_id])
    if not product or product["seller_id"] != user.pk:
        raise Http404("Listing not found.")
    if product["visibility"] == "removed_by_admin":
        raise PermissionDenied("Administrator-removed listings cannot be edited.")
    if one("SELECT 1 FROM transactions WHERE product_id=%s AND status<>'cancelled'", [product_id]):
        raise ListingConflict("This listing has an active order or completed sale and cannot be edited.")
    draft = one("SELECT * FROM app_listing_drafts WHERE product_id=%s", [product_id])
    if (product["current_revision_no"] or 0) != expected_revision or (draft["version"] if draft else 0) != draft_version:
        raise ListingConflict("This listing or draft changed in another session. Reload before saving again.")
    return product, draft


def _prepare(uploads):
    uploads = list(uploads)
    if len(uploads) > 6:
        raise ValidationError("A listing can have at most six images.")
    return [validate_image(upload) for upload in uploads]


def _new_or_locked(user, product_id, expected_revision, draft_version):
    # Lock account before product, matching the database-wide actor ordering contract.
    record = one("SELECT status,is_active,is_member(user_id,'seller') AS seller FROM users WHERE user_id=%s FOR UPDATE", [user.pk])
    if not record or record["status"] != "active" or not record["is_active"] or not record["seller"]:
        raise PermissionDenied("An active seller is required.")
    if product_id is None:
        if expected_revision or draft_version:
            raise ListingConflict("Invalid new-listing version.")
        product_id = one("INSERT INTO products(seller_id) VALUES(%s) RETURNING product_id", [user.pk])["product_id"]
    return _editable(user, product_id, expected_revision, draft_version)


def _current_images(product, retain_images):
    return rows("SELECT * FROM product_images WHERE product_id=%s AND revision_no=%s ORDER BY sort_order",
                [product["product_id"], product["current_revision_no"]]) if retain_images and product["current_revision_no"] else []


def save_draft(user, fields, uploads=(), *, product_id=None, expected_revision=0, draft_version=0,
               retain_images=True, clear_draft_images=False):
    safe_fields = {}
    for name, limit in FIELDS.items():
        value = str(fields.get(name, ""))
        if len(value) > limit:
            raise ValidationError(f"{name.replace('_', ' ').title()} is too long, including for a draft.")
        safe_fields[name] = value
    prepared = _prepare(uploads)
    written = []
    try:
        with actor_transaction(user, "Save private listing draft"):
            product, draft = _new_or_locked(user, product_id, expected_revision, draft_version)
            discarded = draft["payload"].get("images", []) if draft and clear_draft_images else []
            images = draft["payload"].get("images", []) if draft and not clear_draft_images else []
            if len(images) + len(prepared) + len(_current_images(product, retain_images)) > 6:
                raise ValidationError("A listing can have at most six images, including retained images.")
            for image in prepared:
                written.append(store_image(image, private=True))
            payload = {"fields": safe_fields, "images": images + written, "retain_images": bool(retain_images)}
            saved = one("""INSERT INTO app_listing_drafts(product_id,seller_id,payload) VALUES(%s,%s,%s::jsonb)
                ON CONFLICT(product_id) DO UPDATE SET payload=excluded.payload,version=app_listing_drafts.version+1,
                    updated_at=clock_timestamp() RETURNING version""", [product["product_id"], user.pk, json.dumps(payload)])
            for image in discarded:
                transaction.on_commit(lambda image=image: remove_stored(image, private=True), robust=True)
            return product["product_id"], saved["version"]
    except Exception:
        for image in written:
            remove_stored(image, private=True)
        raise


def publish_listing(user, fields, uploads=(), *, product_id=None, expected_revision=0, draft_version=0,
                    retain_images=True, clear_draft_images=False):
    prepared = _prepare(uploads)
    written = []
    try:
        with actor_transaction(user, "Submit immutable listing revision for scanning"):
            product, draft = _new_or_locked(user, product_id, expected_revision, draft_version)
            if not one("SELECT 1 FROM categories WHERE category_id=%s AND is_active", [fields["category_id"]]):
                raise ValidationError("Select an active category.")
            prior = _current_images(product, retain_images)
            all_draft_images = draft["payload"].get("images", []) if draft else []
            draft_images = [] if clear_draft_images else all_draft_images
            if len(prior) + len(draft_images) + len(prepared) > 6:
                raise ValidationError("A listing can have at most six images, including retained images.")
            currency = one("SELECT currency FROM marketplace_settings WHERE singleton")["currency"]
            revision = (product["current_revision_no"] or 0) + 1
            rows("""INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,price,
                    original_price,currency,condition,location,text_fingerprint)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", [
                product["product_id"], revision, fields["category_id"], fields["title"], fields["description"],
                fields["price"], fields.get("original_price"), currency, fields["condition"], fields["location"],
                text_fingerprint(fields["title"], fields["description"]),
            ])
            for image in prior:
                written.append(copy_stored_image(image))
            for image in draft_images:
                written.append(copy_stored_image(image, source_private=True))
            for image in prepared:
                written.append(store_image(image))
            for position, image in enumerate(written):
                rows("""INSERT INTO product_images(product_id,revision_no,storage_key,sort_order,content_type,
                    byte_size,content_sha256,width,height) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""", [
                    product["product_id"], revision, image["storage_key"], position, image["content_type"],
                    image["byte_size"], image["content_sha256"], image["width"], image["height"],
                ])
            # Existing visibility is preserved; publication cannot restore an administrator removal.
            rows("UPDATE products SET current_revision_no=%s,availability='available' WHERE product_id=%s",
                 [revision, product["product_id"]])
            rows("DELETE FROM app_listing_drafts WHERE product_id=%s", [product["product_id"]])
            for image in all_draft_images:
                transaction.on_commit(lambda image=image: remove_stored(image, private=True), robust=True)
            return product["product_id"], revision
    except Exception:
        for image in written:
            remove_stored(image)
        raise


def withdraw_listing(user, product_id):
    with actor_transaction(user, "Seller withdrew listing"):
        record = one("SELECT status,is_active,is_member(user_id,'seller') AS seller FROM users WHERE user_id=%s FOR UPDATE", [user.pk])
        if not record or record["status"] != "active" or not record["is_active"] or not record["seller"]:
            raise PermissionDenied
        product = one("SELECT * FROM products WHERE product_id=%s FOR UPDATE", [product_id])
        if not product or product["seller_id"] != user.pk:
            raise Http404
        if product["visibility"] == "removed_by_admin":
            raise PermissionDenied("Only an administrator can change this removal.")
        if product["availability"] != "available":
            raise ListingConflict("Only an available listing can be withdrawn.")
        rows("UPDATE products SET visibility='removed_by_seller' WHERE product_id=%s", [product_id])
