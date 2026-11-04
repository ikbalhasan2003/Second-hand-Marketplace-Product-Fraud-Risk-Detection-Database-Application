"""Administrator operations; database triggers own their atomic audit/history events."""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from accounts.access import has_role
from marketplace.db import actor_transaction, one, rows


def require_admin(user):
    if not has_role(user, "administrator") or user.status != "active":
        raise PermissionDenied("An active administrator is required.")


def reason_text(reason):
    reason = reason.strip()
    if not 1 <= len(reason) <= 5000:
        raise ValidationError("Provide an action reason of 1 to 5000 characters.")
    return reason


def record_decision(user, product_id, revision_no, verdict, reason, evidence, expected_head=None, report_id=None):
    require_admin(user)
    reason = reason_text(reason)
    if verdict not in ("fraud", "legitimate", "unresolved") or not evidence.strip():
        raise ValidationError("Choose a verdict and describe its evidence basis.")
    if len(evidence) > 10000:
        raise ValidationError("Evidence summaries must fit within 10000 characters.")
    with actor_transaction(user, reason):
        product = one("SELECT seller_id FROM products WHERE product_id=%s", [product_id])
        if not product:
            raise Http404
        rows("SELECT user_id FROM users WHERE user_id=ANY(%s) ORDER BY user_id FOR UPDATE", [[user.pk, product["seller_id"]]])
        rows("SELECT product_id FROM products WHERE product_id=%s FOR UPDATE", [product_id])
        if not one("SELECT 1 FROM product_revisions WHERE product_id=%s AND revision_no=%s", [product_id, revision_no]):
            raise Http404
        head = one("SELECT review_id FROM moderation_reviews WHERE product_id=%s AND revision_no=%s ORDER BY reviewed_at DESC,review_id DESC LIMIT 1", [product_id, revision_no])
        if (head["review_id"] if head else None) != expected_head:
            raise ValidationError("The decision chain changed. Review its latest decision before appending a correction.")
        review = one("""INSERT INTO moderation_reviews(product_id,revision_no,report_id,reviewer_id,verdict,reason,evidence_summary,supersedes_review_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING review_id""",
                     [product_id, revision_no, report_id, user.pk, verdict, reason, evidence.strip(), expected_head])
        return one("SELECT audit_id FROM admin_audit_logs WHERE review_id=%s ORDER BY audit_id DESC LIMIT 1", [review["review_id"]])["audit_id"]


def moderate_target(user, product_id, action, reason, expected, report_id=None, outcome=""):
    require_admin(user)
    reason = reason_text(reason)
    with actor_transaction(user, reason):
        product = one("SELECT seller_id FROM products WHERE product_id=%s", [product_id])
        if not product:
            raise Http404
        rows("SELECT user_id FROM users WHERE user_id=ANY(%s) ORDER BY user_id FOR UPDATE", [[user.pk, product["seller_id"]]])
        current = one("SELECT * FROM products WHERE product_id=%s FOR UPDATE", [product_id])
        if action in ("remove", "restore"):
            if current["visibility"] != expected:
                raise ValidationError("Listing visibility changed. Reload the case before acting.")
            visibility = "removed_by_admin" if action == "remove" else "visible"
            if action == "restore" and expected != "removed_by_admin":
                raise ValidationError("Only an administrator removal can be restored here.")
            if visibility == expected:
                raise ValidationError("The listing already has this visibility.")
            rows("UPDATE products SET visibility=%s WHERE product_id=%s", [visibility, product_id])
            target, value = "product_id", product_id
        elif action in ("block", "unblock"):
            seller = one("SELECT status FROM users WHERE user_id=%s", [product["seller_id"]])
            status = "blocked" if action == "block" else "active"
            if seller["status"] != expected or (action == "unblock" and expected != "blocked") or (action == "block" and expected != "active") or status == expected:
                raise ValidationError("Account status changed or this transition is not available.")
            if one("SELECT 1 FROM users_groups ug JOIN auth_group g ON g.id=ug.group_id WHERE ug.user_id=%s AND g.name='administrator'", [product["seller_id"]]):
                raise ValidationError("Administrator accounts require controlled provisioning.")
            rows("UPDATE users SET status=%s,deactivated_at=NULL WHERE user_id=%s", [status, product["seller_id"]])
            target, value = "user_id", product["seller_id"]
        elif action in ("reviewing", "resolved", "dismissed"):
            report = one("SELECT status FROM fraud_reports WHERE report_id=%s AND product_id=%s FOR UPDATE", [report_id, product_id])
            if not report or report["status"] != expected:
                raise ValidationError("Report status changed. Reload the case before acting.")
            if action in ("resolved", "dismissed") and not outcome.strip():
                raise ValidationError("Provide a reporter-facing outcome when closing a report.")
            rows("UPDATE fraud_reports SET status=%s,assigned_admin_id=%s,public_outcome=%s WHERE report_id=%s", [action, user.pk, outcome.strip() or None, report_id])
            target, value = "report_id", report_id
        else:
            raise ValidationError("Choose a supported moderation action.")
        return one("SELECT audit_id FROM admin_audit_logs WHERE " + target + "=%s ORDER BY audit_id DESC LIMIT 1", [value])["audit_id"]


def create_ruleset(user, version, schema_id, medium, high, max_age_hours, reason):
    require_admin(user)
    reason = reason_text(reason)
    if not 0 <= medium < high <= 100 or not 1 <= max_age_hours <= 168:
        raise ValidationError("Require 0 ≤ Medium < High ≤ 100 and an age of 1 to 168 hours.")
    with actor_transaction(user, reason):
        ruleset = one("INSERT INTO risk_rulesets(version,feature_schema_id,created_by,max_assessment_age) VALUES(%s,%s,%s,%s) RETURNING ruleset_id", [version, schema_id, user.pk, timedelta(hours=max_age_hours)])
        for key, value in (("medium_min", medium), ("high_min", high)):
            rows("INSERT INTO risk_rules(ruleset_id,rule_key,numeric_value,description) VALUES(%s,%s,%s,%s)", [ruleset["ruleset_id"], key, value, "Minimum inclusive score for this risk band"])
        rows("SELECT app_audit_ruleset_draft(%s)", [ruleset["ruleset_id"]])
        return ruleset["ruleset_id"]


def activate_configuration(user, model_id, ruleset_id, reason, expected_model=None, expected_ruleset=None):
    require_admin(user)
    reason = reason_text(reason)
    model = one("SELECT m.*,f.version AS schema_version FROM risk_models m JOIN feature_schemas f USING(feature_schema_id) WHERE m.model_id=%s", [model_id])
    if not model:
        raise ValidationError("Select a registered model.")
    from ml.training.artifacts import load_trusted_pipeline
    try:
        load_trusted_pipeline(settings.ARTIFACT_ROOT, model["artifact_key"], model["artifact_sha256"], model["schema_version"], model["dependency_manifest"], model["class_mapping"])
    except (OSError, ValueError, ImportError) as error:
        raise ValidationError("Trusted artifact verification failed. Review its registration, checksum and dependencies.") from error
    with actor_transaction(user, reason):
        # The SQL activation API takes this same advisory lock before changing either version.
        rows("SELECT pg_advisory_xact_lock(719241,1)")
        current_model = one("SELECT model_id FROM risk_models WHERE state='active'")
        current_rules = one("SELECT ruleset_id FROM risk_rulesets WHERE state='active'")
        if (current_model["model_id"] if current_model else None) != expected_model or (current_rules["ruleset_id"] if current_rules else None) != expected_ruleset:
            raise ValidationError("The active configuration changed. Review the current pair before activation.")
        rows("SELECT activate_risk_configuration(%s,%s)", [model_id, ruleset_id])

