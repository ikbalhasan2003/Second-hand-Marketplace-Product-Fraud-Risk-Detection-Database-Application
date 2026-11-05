import io
import json
import zipfile
import uuid

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.access import require_role
from marketplace.db import actor_transaction, one, rows
from marketplace.services.admin_exports import create_reviewed_export, reviewed_candidates
from marketplace.services.moderation import activate_configuration, create_ruleset, moderate_target, record_decision, reason_text
from marketplace.services.moderation import assign_report, request_rescan
from marketplace.services.orders import transition_order
from .forms import ActivationForm, AuditFilterForm, DecisionForm, ExportForm, QueueFilterForm, RulesetForm


def error_message(error):
    return "; ".join(error.messages) if isinstance(error, ValidationError) else "This action conflicted with the current state or could not commit its audit. Review the current record before trying again."


@require_role("administrator")
def dashboard(request):
    error_message_text = None
    if request.method == "POST":
        try:
            audit = request_rescan(request.user, int(request.POST.get("product_id", "0")), request.POST.get("request_key"), request.POST.get("reason", ""))
            return redirect(f"/admin-app/audit-log/{audit}/")
        except (DatabaseError, ValidationError, ValueError) as error:
            error_message_text = error_message(error)
    counts = one("""SELECT (SELECT count(*) FROM admin_review_queue) AS queue,
        (SELECT count(*) FROM products) AS total_listings,
        (SELECT count(*) FROM current_listing_risk WHERE assessment_state='ready' AND risk_level='medium') AS medium_risk,
        (SELECT count(*) FROM current_listing_risk WHERE assessment_state='ready' AND risk_level='high') AS high_risk,
        (SELECT count(*) FROM fraud_reports WHERE status IN ('pending','reviewing')) AS reports,
        (SELECT count(*) FROM transactions WHERE status='disputed') AS disputes,
        (SELECT count(*) FROM risk_scan_jobs WHERE status='failed') AS failed_scans""")
    return render(request, "admin_app/dashboard.html", {"title": "Marketplace oversight", "counts": counts,
        "refreshed_at": timezone.now(), "request_key": request.POST.get("request_key") or uuid.uuid4(), "error": error_message_text,
        "metrics": [(key.replace("_", " ").title(), value) for key, value in counts.items()],
        "operations": rows("SELECT status,count(*) AS n,min(created_at) AS oldest FROM risk_scan_jobs WHERE status IN ('queued','processing','failed') GROUP BY status ORDER BY status"),
        "failed_jobs": rows("SELECT job_id,product_id,revision_no,error_code,attempts,retry_at FROM risk_scan_jobs WHERE status='failed' ORDER BY job_id DESC LIMIT 20"),
        "queue_preview": rows("SELECT * FROM admin_review_queue ORDER BY priority_group,oldest_waiting_at,product_id LIMIT 5"),
        "active_model": one("SELECT version FROM risk_models WHERE state='active'"), "active_rules": one("SELECT version FROM risk_rulesets WHERE state='active'"),
        "recent": rows("SELECT * FROM admin_audit_logs ORDER BY occurred_at DESC,audit_id DESC LIMIT 8"),
        "campaigns": rows("SELECT * FROM risk_rescan_campaigns WHERE status<>'completed' ORDER BY campaign_id LIMIT 10")}, status=409 if error_message_text else 200)


@require_role("administrator")
def queue(request):
    filters = QueueFilterForm(request.GET)
    source = request.GET.get("source", "")
    suffix = {"reports": " WHERE open_report_count>0", "ai": " WHERE current_high_risk", "combined": " WHERE current_high_risk AND open_report_count>0"}.get(source, "")
    if request.GET.get("type") == "order-dispute":
        suffix = " WHERE false"
    clauses, params = [], []
    if filters.is_valid():
        data = filters.cleaned_data
        if data.get("risk") == "unassessed":
            clauses.append("assessment_state<>'ready'")
        elif data.get("risk"):
            clauses.append("assessment_state='ready' AND risk_level=%s")
            params.append(data["risk"])
        if data.get("age_days") is not None:
            clauses.append("oldest_waiting_at<=clock_timestamp()-(%s * interval '1 day')")
            params.append(data["age_days"])
        report_clauses = ["f.product_id=admin_review_queue.product_id", "f.status IN ('pending','reviewing')"]
        if data.get("status"):
            report_clauses.append("f.status=%s")
            params.append(data["status"])
        if data.get("assignee"):
            report_clauses.append("f.assigned_admin_id=%s")
            params.append(data["assignee"])
        if data.get("unassigned"):
            report_clauses.append("f.assigned_admin_id IS NULL")
        if data.get("status") or data.get("assignee") or data.get("unassigned"):
            clauses.append("EXISTS(SELECT 1 FROM fraud_reports f WHERE " + " AND ".join(report_clauses) + ")")
    else:
        clauses.append("false")
    if clauses:
        suffix += (" AND " if suffix else " WHERE ") + " AND ".join(clauses)
    total = one("SELECT count(*) AS n FROM admin_review_queue" + suffix, params)["n"]
    page = Paginator(range(total), 25).get_page(request.GET.get("page"))
    result = rows("SELECT * FROM admin_review_queue" + suffix + " ORDER BY priority_group,oldest_waiting_at,product_id LIMIT 25 OFFSET %s", params + [(page.number - 1) * 25])
    dispute_count = one("SELECT count(*) AS n FROM transactions WHERE status='disputed'")["n"]
    dispute_page = Paginator(range(dispute_count), 25).get_page(request.GET.get("dispute_page"))
    disputes = rows("SELECT * FROM seller_order_history WHERE status='disputed' ORDER BY created_at,transaction_id LIMIT 25 OFFSET %s", [(dispute_page.number - 1) * 25])
    query = request.GET.copy()
    query.pop("page", None)
    dispute_query = request.GET.copy()
    dispute_query.pop("dispute_page", None)
    return render(request, "admin_app/queue.html", {"title": "Moderation queue", "cases": result, "page": page, "source": source, "form": filters,
        "disputes": disputes, "dispute_page": dispute_page, "query": query.urlencode(),
        "dispute_query": dispute_query.urlencode()})


def case_context(product_id, revision, form=None):
    product = one("SELECT p.*,u.full_name,u.status AS seller_status FROM products p JOIN users u ON u.user_id=p.seller_id WHERE product_id=%s", [product_id])
    if not product:
        raise Http404
    revision = revision or product["current_revision_no"]
    content = one("SELECT * FROM product_revisions WHERE product_id=%s AND revision_no=%s", [product_id, revision])
    if not content:
        raise Http404
    decisions = rows("SELECT * FROM moderation_reviews WHERE product_id=%s AND revision_no=%s ORDER BY reviewed_at DESC,review_id DESC", [product_id, revision])
    head = decisions[0]["review_id"] if decisions else None
    return {"title": f"Case · listing #{product_id} · revision {revision}", "product": product, "revision": content,
        "revisions": rows("SELECT revision_no,title FROM product_revisions WHERE product_id=%s ORDER BY revision_no DESC", [product_id]),
        "decisions": decisions, "form": form or DecisionForm(initial={"revision_no": revision, "expected_head": head}),
        "administrators": rows("SELECT u.user_id,u.full_name FROM users u JOIN users_groups ug ON ug.user_id=u.user_id JOIN auth_group g ON g.id=ug.group_id WHERE g.name='administrator' AND u.status='active' AND u.is_active ORDER BY u.full_name,u.user_id"),
        "reports": rows("SELECT * FROM fraud_reports WHERE product_id=%s AND revision_no=%s ORDER BY report_id", [product_id, revision]),
        "attachments": rows("SELECT a.*,f.revision_no FROM report_attachments a JOIN fraud_reports f USING(report_id) WHERE f.product_id=%s AND f.revision_no=%s", [product_id, revision]),
        "assessments": rows("SELECT j.job_id,j.status,j.feature_as_of,j.model_id,j.ruleset_id,l.risk_score,l.risk_level,l.observed_factors FROM risk_scan_jobs j LEFT JOIN risk_logs l USING(job_id) WHERE j.product_id=%s AND j.revision_no=%s ORDER BY j.job_id DESC LIMIT 10", [product_id, revision]),
        "audits": rows("SELECT audit_id,action_type FROM admin_audit_logs WHERE product_id=%s ORDER BY audit_id DESC LIMIT 10", [product_id])}


@require_role("administrator")
def case(request, product_id):
    try:
        revision = int(request.GET["revision"]) if request.GET.get("revision") else None
    except ValueError:
        raise Http404
    form = DecisionForm(request.POST) if request.method == "POST" and request.POST.get("operation") == "decision" else None
    if request.method == "POST":
        try:
            operation = request.POST.get("operation")
            if operation == "decision":
                if form.is_valid():
                    audit = record_decision(request.user, product_id, **form.cleaned_data)
                else:
                    return render(request, "admin_app/case.html", case_context(product_id, revision, form), status=400)
            elif operation == "moderate":
                report_id = int(request.POST["report_id"]) if request.POST.get("report_id") else None
                audit = moderate_target(request.user, product_id, request.POST.get("action"), request.POST.get("reason", ""), request.POST.get("expected", ""), report_id, request.POST.get("outcome", ""))
            elif operation == "assign":
                assignee = request.user.pk if request.POST.get("assign_to_me") else int(request.POST.get("assignee_id", "0"))
                expected = int(request.POST["expected_assignee"]) if request.POST.get("expected_assignee") else None
                audit = assign_report(request.user, product_id, int(request.POST.get("report_id", "0")), assignee, expected, request.POST.get("expected_status"), request.POST.get("reason", ""))
            else:
                raise ValidationError("Choose an explicit case action.")
            messages.success(request, f"Action committed. Audit receipt #{audit}.")
            return redirect(f"/admin-app/audit-log/{audit}/")
        except (DatabaseError, ValidationError, ValueError) as error:
            context = case_context(product_id, revision, form)
            context["error"] = error_message(error)
            return render(request, "admin_app/case.html", context, status=409)
    return render(request, "admin_app/case.html", case_context(product_id, revision))


@require_role("administrator")
def dispute(request, order_id):
    order = one("SELECT * FROM seller_order_history WHERE transaction_id=%s", [order_id])
    if not order:
        raise Http404
    context = {"title": f"Order dispute #{order_id}", "order": order,
               "events": rows("SELECT * FROM order_status_history WHERE transaction_id=%s ORDER BY event_id", [order_id])}
    if request.method == "POST":
        try:
            if order["status"] != "disputed" or request.POST.get("status") not in ("completed", "cancelled") or not request.POST.get("evidence", "").strip():
                raise ValidationError("Review a disputed order, choose Completed or Cancelled, and record the evidence basis.")
            reason = reason_text(request.POST.get("reason", "")) + "\nEvidence: " + request.POST["evidence"].strip()
            transition_order(request.user, order_id, request.POST["status"], reason, request.POST.get("expected_status"))
            audit = one("SELECT audit_id FROM admin_audit_logs WHERE transaction_id=%s ORDER BY audit_id DESC LIMIT 1", [order_id])
            return redirect(f"/admin-app/audit-log/{audit['audit_id']}/")
        except (DatabaseError, ValidationError) as error:
            context["error"] = error_message(error)
            return render(request, "admin_app/dispute.html", context, status=409)
    return render(request, "admin_app/dispute.html", context)


@require_role("administrator")
def models(request, model_id=None, ruleset_id=None):
    form = ActivationForm(request.POST or None)
    active_model = one("SELECT * FROM risk_models WHERE state='active'")
    active_rules = one("SELECT * FROM risk_rulesets WHERE state='active'")
    form.initial.update({"expected_model": active_model["model_id"] if active_model else None, "expected_ruleset": active_rules["ruleset_id"] if active_rules else None})
    context = {"title": "Models and rules", "models": rows("SELECT m.*,f.version AS schema_version,d.version AS dataset_version FROM risk_models m JOIN feature_schemas f USING(feature_schema_id) JOIN dataset_versions d USING(dataset_id) ORDER BY model_id DESC"),
        "rulesets": rows("SELECT * FROM risk_rulesets ORDER BY ruleset_id DESC"), "active_model": active_model, "active_rules": active_rules, "form": form,
        "campaigns": rows("SELECT * FROM risk_rescan_campaigns ORDER BY campaign_id DESC LIMIT 10")}
    if request.method == "POST" and form.is_valid():
        try:
            data = form.cleaned_data.copy()
            data.pop("confirm")
            audit = activate_configuration(request.user, **data)
            messages.success(request, "Configuration activated. Durable reassessment campaigns are queued; results update asynchronously.")
            return redirect(f"/admin-app/audit-log/{audit}/")
        except (DatabaseError, ValidationError) as error:
            context["error"] = error_message(error)
            return render(request, "admin_app/models.html", context, status=409)
    if model_id:
        context["selected"] = one("SELECT * FROM risk_models WHERE model_id=%s", [model_id])
        if not context["selected"]:
            raise Http404
        context["evaluations"] = rows("SELECT * FROM model_evaluation_metrics WHERE model_id=%s ORDER BY partition,slice_key", [model_id])
        context["metadata"] = json.dumps(context["selected"], default=str, indent=2)
        # The trusted report contains baseline comparisons and safe false-positive examples.
        try:
            from ml.datasets.io import checksum
            root = settings.ARTIFACT_ROOT.resolve()
            directory = (root / context["selected"]["artifact_key"]).resolve().parent
            if not directory.is_relative_to(root):
                raise ValueError("Invalid artifact directory")
            registration = json.loads((directory / "model.json").read_text(encoding="utf-8"))
            report_path = directory / "evaluation.json"
            if registration["artifact_sha256"] != context["selected"]["artifact_sha256"] or checksum(report_path) != registration["evaluation_sha256"]:
                raise ValueError("Evaluation checksum mismatch")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            context["evaluation_notes"] = report["limitations"]
            context["synthetic_only"] = report["synthetic_only"]
            context["report_rows"] = [dict(values, algorithm=algorithm, partition=partition, slice_key=slice_key)
                for algorithm, partitions in report["models"].items() for partition, slices in partitions.items() for slice_key, values in slices.items()]
        except (OSError, ValueError, KeyError, TypeError):
            context["report_unavailable"] = True
    if ruleset_id:
        context["selected_rules"] = one("SELECT * FROM risk_rulesets WHERE ruleset_id=%s", [ruleset_id])
        if not context["selected_rules"]:
            raise Http404
        context["rule_values"] = rows("SELECT * FROM risk_rules WHERE ruleset_id=%s ORDER BY rule_key", [ruleset_id])
        context["ruleset_receipt"] = one("SELECT audit_id,occurred_at FROM admin_audit_logs WHERE ruleset_id=%s ORDER BY audit_id DESC LIMIT 1", [ruleset_id])
    return render(request, "admin_app/models.html", context)


@require_role("administrator")
def ruleset_new(request):
    form = RulesetForm(request.POST or None)
    context = {"title": "Create a ruleset version", "form": form, "schemas": rows("SELECT * FROM feature_schemas ORDER BY feature_schema_id")}
    if request.method == "POST" and form.is_valid():
        try:
            ruleset_id = create_ruleset(request.user, **form.cleaned_data)
            return redirect(f"/admin-app/rulesets/{ruleset_id}/")
        except (DatabaseError, ValidationError) as error:
            context["error"] = error_message(error)
            return render(request, "admin_app/ruleset_form.html", context, status=409)
    return render(request, "admin_app/ruleset_form.html", context)


@require_role("administrator")
def audit_log(request, audit_id=None):
    if audit_id:
        event = one("SELECT * FROM admin_audit_logs WHERE audit_id=%s", [audit_id])
        if not event:
            raise Http404
        return render(request, "admin_app/audit.html", {"title": f"Audit receipt #{audit_id}", "event": event,
            "before": json.dumps(event["before_data"], ensure_ascii=False, indent=2), "after": json.dumps(event["after_data"], ensure_ascii=False, indent=2)})
    form = AuditFilterForm(request.GET)
    where, params = [], []
    if form.is_valid():
        for name, clause in (("actor", "admin_id=%s"), ("event", "audit_id=%s"), ("action", "action_type=%s"), ("start", "occurred_at>=%s"), ("end", "occurred_at<=%s")):
            if form.cleaned_data.get(name):
                where.append(clause)
                params.append(form.cleaned_data[name])
        if form.cleaned_data.get("target_type"):
            where.append(form.cleaned_data["target_type"] + "_id=%s")
            params.append(form.cleaned_data["target_id"])
    else:
        where.append("false")
    suffix = " WHERE " + " AND ".join(where) if where else ""
    count = one("SELECT count(*) AS n FROM admin_audit_logs" + suffix, params)["n"]
    page = Paginator(range(count), 25).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    events = rows("SELECT * FROM admin_audit_logs" + suffix + " ORDER BY occurred_at DESC,audit_id DESC LIMIT 25 OFFSET %s", params + [(page.number - 1) * 25])
    return render(request, "admin_app/audit.html", {"title": "Audit log · read only", "events": events, "form": form, "page": page, "query": query.urlencode()})


@require_role("administrator")
def exports(request, dataset_id=None):
    form = ExportForm(request.POST or None, initial={"cutoff": timezone.now(), "seed": 42})
    context = {"title": "Administrator dataset exports", "form": form,
        "datasets": rows("SELECT d.*,f.version AS schema_version,(SELECT count(*) FROM dataset_records r WHERE r.dataset_id=d.dataset_id) AS record_count FROM dataset_versions d JOIN feature_schemas f USING(feature_schema_id) ORDER BY dataset_id DESC")}
    preview_cutoff = form.cleaned_data["cutoff"] if form.is_valid() else timezone.now()
    schema, candidates, excluded = reviewed_candidates(preview_cutoff)
    context.update({"schema": schema, "eligible": len(candidates), "excluded": excluded})
    if request.method == "POST" and form.is_valid():
        try:
            result = create_reviewed_export(request.user, **form.cleaned_data)
            return redirect(f"/admin-app/exports/{result}/")
        except (DatabaseError, ValidationError, ValueError, OSError) as error:
            context["error"] = error_message(error)
            return render(request, "admin_app/exports.html", context, status=409)
    if dataset_id:
        context["dataset"] = one("SELECT * FROM dataset_versions WHERE dataset_id=%s", [dataset_id])
        if not context["dataset"]:
            raise Http404
        context["sources"] = rows("SELECT s.source_type,r.is_synthetic,count(*) AS n FROM dataset_records r JOIN dataset_sources s USING(source_id) WHERE dataset_id=%s GROUP BY s.source_type,r.is_synthetic", [dataset_id])
        context["receipt"] = one("SELECT audit_id FROM admin_audit_logs WHERE dataset_id=%s ORDER BY audit_id DESC LIMIT 1", [dataset_id])
    return render(request, "admin_app/exports.html", context)


@require_role("administrator")
@require_POST
def export_download(request, dataset_id):
    dataset = one("SELECT * FROM dataset_versions WHERE dataset_id=%s AND state='frozen'", [dataset_id])
    if not dataset:
        raise Http404
    try:
        reason = reason_text(request.POST.get("reason", ""))
        from ml.datasets.io import load_dataset
        root = settings.ARTIFACT_ROOT.resolve()
        manifest_path = (root / dataset["manifest_key"]).resolve()
        if not manifest_path.is_relative_to(root) or manifest_path.name != "manifest.json":
            raise ValueError("Invalid registered manifest path")
        _, manifest = load_dataset(manifest_path.parent)
        if manifest["dataset_version"] != dataset["version"] or manifest["dataset_sha256"] != dataset["dataset_sha256"]:
            raise ValueError("Registered dataset checksum mismatch")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for name in ("records.jsonl", "manifest.json"):
                output.write(manifest_path.parent / name, name)
        with actor_transaction(request.user, reason):
            receipt = one("SELECT app_audit_dataset_download(%s,%s) AS audit_id", [dataset_id, manifest["dataset_sha256"]])
        archive.seek(0)
        response = FileResponse(archive, as_attachment=True, filename=f"dataset-{dataset_id}.zip", content_type="application/zip")
        response["Cache-Control"] = "private, no-store"
        response["X-Audit-Receipt"] = str(receipt["audit_id"])
        return response
    except (DatabaseError, ValidationError, ValueError, OSError) as error:
        return render(request, "admin_app/exports.html", {"title": "Export unavailable", "error": error_message(error)}, status=409)
