import hashlib
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from accounts.access import has_role, require_role
from marketplace.db import one, rows
from marketplace.services.appeals import submit_appeal, decide_appeal
from marketplace.uploads import _path


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def appeals(request):
    error = None
    if request.method == "POST":
        try:
            submit_appeal(request.user, request.POST.get("reason", ""), request.FILES.getlist("evidence"))
            return redirect("account_appeals")
        except ValidationError as exc:
            error = "; ".join(exc.messages)
    records = rows("SELECT * FROM account_appeals WHERE user_id=%s ORDER BY appeal_id DESC", [request.user.pk])
    for appeal in records:
        appeal["evidence"] = rows("SELECT evidence_id FROM account_appeal_evidence WHERE appeal_id=%s", [appeal["appeal_id"]])
    return render(request, "accounts/appeals.html", {"title": "Account appeals", "appeals": records, "error": error}, status=400 if error else 200)


@require_role("administrator")
@require_http_methods(["GET", "POST"])
def review(request):
    error = None
    if request.method == "POST":
        try:
            decide_appeal(request.user, int(request.POST.get("appeal_id", "0")), request.POST.get("status"), request.POST.get("notes", ""), request.POST.get("expected"))
            return redirect("admin_appeals")
        except (ValidationError, ValueError) as exc:
            error = str(exc)
    from django.core.paginator import Paginator
    page = Paginator(rows("SELECT a.*,u.full_name FROM account_appeals a JOIN users u USING(user_id) ORDER BY (a.status IN ('pending','reviewing')) DESC,a.appeal_id DESC"), 25).get_page(request.GET.get("page"))
    for appeal in page:
        appeal["evidence"] = rows("SELECT evidence_id FROM account_appeal_evidence WHERE appeal_id=%s", [appeal["appeal_id"]])
    return render(request, "admin_app/appeals.html", {"title": "Unblock appeals", "appeals": page, "page": page, "error": error}, status=409 if error else 200)


@login_required
@never_cache
@require_GET
def evidence(request, evidence_id):
    record = one("SELECT e.*,a.user_id FROM account_appeal_evidence e JOIN account_appeals a USING(appeal_id) WHERE evidence_id=%s", [evidence_id])
    if not record:
        raise Http404
    if record["user_id"] != request.user.pk and not (has_role(request.user, "administrator") and request.user.status == "active"):
        raise PermissionDenied
    try:
        stream = _path(record["storage_key"], private=True).open("rb")
    except OSError:
        raise Http404
    content = stream.read(5242881)
    stream.close()
    if len(content) != record["byte_size"] or hashlib.sha256(content).hexdigest() != record["content_sha256"]:
        raise Http404
    import io
    response = FileResponse(io.BytesIO(content), content_type=record["content_type"], as_attachment=True, filename="appeal-evidence")
    response["X-Content-Type-Options"] = "nosniff"
    return response
