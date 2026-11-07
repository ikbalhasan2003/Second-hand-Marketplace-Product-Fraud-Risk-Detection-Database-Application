import hashlib
import json
import uuid
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from accounts.access import has_role
from marketplace.db import actor_transaction, one, rows


def review_state(risk):
    return [risk.get("assessment_state"), risk.get("risk_level"), str(risk.get("risk_id"))]


def place_order(user, product_id, revision_no, request_key, acknowledge=False, review_token=None):
    if not has_role(user, "buyer") or user.status != "active":
        raise PermissionDenied
    try:
        request_key = uuid.UUID(str(request_key))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("A valid purchase request key is required.") from error
    fingerprint = hashlib.sha256(json.dumps([product_id, revision_no], separators=(",", ":")).encode()).hexdigest()
    with actor_transaction(user, "Buyer placed purchase agreement"):
        current_user = one("SELECT status,is_active FROM users WHERE user_id=%s", [user.pk])
        if not current_user or current_user["status"] != "active" or not current_user["is_active"]:
            raise PermissionDenied("An active buyer is required.")
        # Reconcile an uncertain submission before considering changed availability/risk.
        rows("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", [f"{user.pk}:{request_key}"])
        existing = one("SELECT transaction_id,product_id,revision_no FROM transactions WHERE buyer_id=%s AND request_key=%s", [user.pk, str(request_key)])
        if existing:
            if (existing["product_id"], existing["revision_no"]) != (product_id, revision_no):
                raise ValidationError("Request key belongs to different purchase terms.")
            return existing["transaction_id"]
        product = one("SELECT seller_id FROM products WHERE product_id=%s", [product_id])
        if not product:
            raise ValidationError("Listing unavailable.")
        rows("SELECT user_id FROM users WHERE user_id=ANY(%s) ORDER BY user_id FOR UPDATE", [[user.pk, product["seller_id"]]])
        rows("SELECT product_id FROM products WHERE product_id=%s FOR UPDATE", [product_id])
        risk = one("SELECT * FROM current_listing_risk WHERE product_id=%s", [product_id])
        if review_token:
            try:
                reviewed = signing.loads(review_token, salt="order-review", max_age=3600)
            except signing.BadSignature as error:
                raise ValidationError("Order review expired. Review the listing again.") from error
            if reviewed != [product_id, revision_no, review_state(risk or {})]:
                raise ValidationError("The listing assessment changed. Review the current listing before ordering.")
        if not risk or risk["assessment_state"] != "ready":
            raise ValidationError("This listing is awaiting a current successful risk assessment.")
        if risk and risk["assessment_state"] == "ready" and risk["risk_level"] == "high" and not acknowledge:
            raise ValidationError("Review the High risk warning and acknowledge it before ordering.")
        return one("SELECT place_order(%s,%s,%s,%s::uuid,%s) AS order_id", [user.pk, product_id, revision_no, str(request_key), fingerprint])["order_id"]


def transition_order(user, order_id, next_status, reason, expected_status):
    if not reason or not reason.strip():
        raise ValidationError("A reason is required.")
    with actor_transaction(user, reason):
        order = one("SELECT t.*,p.seller_id FROM transactions t JOIN products p USING(product_id) WHERE transaction_id=%s", [order_id])
        if not order or (user.pk not in (order["buyer_id"], order["seller_id"]) and not has_role(user, "administrator")):
            raise PermissionDenied
        rows("SELECT user_id FROM users WHERE user_id=ANY(%s) ORDER BY user_id FOR UPDATE", [[order["buyer_id"], order["seller_id"]]])
        rows("SELECT product_id FROM products WHERE product_id=%s FOR UPDATE", [order["product_id"]])
        current = one("SELECT status FROM transactions WHERE transaction_id=%s FOR UPDATE", [order_id])
        if current["status"] != expected_status:
            raise ValidationError("Order changed. Reload its timeline before acting.")
        rows("SELECT transition_order(%s,%s)", [order_id, next_status])
