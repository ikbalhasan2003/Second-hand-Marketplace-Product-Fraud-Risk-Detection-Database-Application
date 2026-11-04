import hashlib
import json
import uuid
from django.core.exceptions import PermissionDenied, ValidationError
from accounts.access import has_role
from marketplace.db import actor_transaction, one, rows


def place_order(user, product_id, revision_no, request_key, acknowledge=False):
    if not has_role(user, "buyer") or user.status != "active":
        raise PermissionDenied
    try:
        request_key = uuid.UUID(str(request_key))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("A valid purchase request key is required.") from error
    fingerprint = hashlib.sha256(json.dumps([product_id, revision_no], separators=(",", ":")).encode()).hexdigest()
    with actor_transaction(user, "Buyer placed purchase agreement"):
        risk = one("SELECT * FROM current_listing_risk WHERE product_id=%s", [product_id])
        if risk and risk["assessment_state"] == "ready" and risk["risk_level"] == "high" and not acknowledge:
            raise ValidationError("Review the High risk warning and acknowledge it before ordering.")
        return one("SELECT place_order(%s,%s,%s,%s::uuid,%s) AS order_id", [user.pk, product_id, revision_no, str(request_key), fingerprint])["order_id"]


def transition_order(user, order_id, next_status, reason, expected_status):
    if not reason.strip():
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
