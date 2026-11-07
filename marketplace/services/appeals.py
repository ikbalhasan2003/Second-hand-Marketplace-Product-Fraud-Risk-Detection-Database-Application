"""Account appeals retain authentication without granting marketplace access."""
from django.core.exceptions import PermissionDenied, ValidationError
from marketplace.db import actor_transaction, one, rows
from marketplace.uploads import validate_image, store_image, remove_stored
from marketplace.services.moderation import require_admin, reason_text


def submit_appeal(user, reason, uploads=()):
    reason = reason.strip()
    if not 10 <= len(reason) <= 5000 or len(uploads) > 3:
        raise ValidationError("Provide a reason of 10 to 5000 characters and up to three evidence images.")
    stored = []
    try:
        with actor_transaction(user, "Account owner submitted unblock appeal"):
            account = one("SELECT status,is_active FROM users WHERE user_id=%s FOR UPDATE", [user.pk])
            if not account or account["status"] != "blocked" or not account["is_active"]:
                raise PermissionDenied("Only a blocked authenticated account may appeal.")
            if one("SELECT 1 FROM account_appeals WHERE user_id=%s AND status IN ('pending','reviewing')", [user.pk]):
                raise ValidationError("You already have an open appeal.")
            validated = [validate_image(upload) for upload in uploads]
            appeal = one("INSERT INTO account_appeals(user_id,reason) VALUES(%s,%s) RETURNING appeal_id", [user.pk, reason])
            for image in validated:
                metadata = store_image(image, private=True)
                stored.append(metadata)
                rows("INSERT INTO account_appeal_evidence(appeal_id,storage_key,content_type,byte_size,content_sha256) VALUES(%s,%s,%s,%s,%s)",
                     [appeal["appeal_id"], metadata["storage_key"], metadata["content_type"], metadata["byte_size"], metadata["content_sha256"]])
            return appeal["appeal_id"]
    except Exception:
        for metadata in stored:
            remove_stored(metadata, private=True)
        raise


def decide_appeal(user, appeal_id, status, notes, expected):
    require_admin(user)
    notes = reason_text(notes)
    if status not in ("reviewing", "approved", "rejected"):
        raise ValidationError("Choose Under Review, Approve and unblock, or Reject.")
    with actor_transaction(user, notes):
        # Match account moderation lock order: account before appeal.
        target = one("SELECT user_id FROM account_appeals WHERE appeal_id=%s", [appeal_id])
        if not target:
            raise ValidationError("Appeal unavailable.")
        rows("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", [target["user_id"]])
        appeal = one("SELECT status FROM account_appeals WHERE appeal_id=%s FOR UPDATE", [appeal_id])
        if appeal["status"] != expected or expected not in ("pending", "reviewing") or expected == status:
            raise ValidationError("Appeal changed or is already closed. Reload before deciding.")
        if status == "approved" and not one("SELECT 1 FROM users WHERE user_id=%s AND status='blocked'", [target["user_id"]]):
            raise ValidationError("Account is no longer blocked. Review before deciding.")
        rows("UPDATE account_appeals SET status=%s,decision_notes=%s WHERE appeal_id=%s", [status, notes, appeal_id])
