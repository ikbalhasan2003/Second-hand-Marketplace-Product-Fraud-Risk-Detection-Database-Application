from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.access import require_role
from accounts.throttle import throttle
from marketplace.db import one, rows
from marketplace.services.listings import FIELDS, ListingConflict, publish_listing, save_draft, withdraw_listing
from marketplace.uploads import _path
from .forms import ListingForm


def _owned(user, product_id):
    product = one("""SELECT p.*,r.title,r.description,r.category_id,r.condition,r.price,r.original_price,r.location,
            r.currency,cr.assessment_state,cr.risk_score,cr.risk_level,cr.predicted_at,rl.observed_factors
        FROM products p LEFT JOIN product_revisions r ON (r.product_id,r.revision_no)=(p.product_id,p.current_revision_no)
        LEFT JOIN current_listing_risk cr ON cr.product_id=p.product_id LEFT JOIN risk_logs rl ON rl.risk_id=cr.risk_id WHERE p.product_id=%s AND p.seller_id=%s""", [product_id, user.pk])
    if not product:
        raise Http404("Listing not found.")
    return product


@require_role("seller")
def dashboard(request):
    if request.method == "POST":
        return edit_listing(request)
    listing_rows = rows("""SELECT p.*,coalesce(r.title,d.payload->'fields'->>'title','Untitled draft') AS title,
        r.price,r.currency,cr.assessment_state,cr.risk_score,cr.risk_level,cr.predicted_at,
        (SELECT observed_factors FROM risk_logs WHERE risk_id=cr.risk_id) AS observed_factors,
        EXISTS(SELECT 1 FROM transactions t WHERE t.product_id=p.product_id AND t.status<>'cancelled') AS locked
        FROM products p LEFT JOIN product_revisions r ON (r.product_id,r.revision_no)=(p.product_id,p.current_revision_no)
        LEFT JOIN app_listing_drafts d ON d.product_id=p.product_id LEFT JOIN current_listing_risk cr ON cr.product_id=p.product_id
        WHERE p.seller_id=%s ORDER BY p.updated_at DESC,p.product_id DESC""", [request.user.pk])
    metrics = {
        "active": sum(row["availability"] in ("available", "reserved") and row["visibility"] == "visible"
                      and row["assessment_state"] == "ready" for row in listing_rows),
        "sold": sum(row["availability"] == "sold" for row in listing_rows),
        "high": sum(row["availability"] in ("available", "reserved") and row["visibility"] == "visible"
                    and row["assessment_state"] == "ready" and row["risk_level"] == "high" for row in listing_rows),
    }
    for name in ("availability", "visibility", "assessment_state", "risk_level"):
        value = request.GET.get(name, "")
        if value:
            listing_rows = [row for row in listing_rows if row.get(name) == value]
    query = request.GET.get("q", "").strip().casefold()
    if query:
        listing_rows = [row for row in listing_rows if query in row["title"].casefold()]
    return render(request, "seller/dashboard.html", {"title": "Seller dashboard", "metrics": metrics,
        "page": Paginator(listing_rows, 20).get_page(request.GET.get("page"))})


@require_role("seller")
def edit_listing(request, product_id=None, force_publish=False):
    product = _owned(request.user, product_id) if product_id else None
    draft = one("SELECT * FROM app_listing_drafts WHERE product_id=%s", [product_id]) if product_id else None
    locked = product and (product["availability"] in ("reserved", "sold") or product["visibility"] == "removed_by_admin"
                          or one("SELECT 1 FROM transactions WHERE product_id=%s AND status<>'cancelled'", [product_id]))
    initial = {name: product.get(name, "") if product else "" for name in FIELDS}
    initial.update({"expected_revision": product["current_revision_no"] or 0 if product else 0,
                    "draft_version": draft["version"] if draft else 0, "retain_images": True})
    if draft:
        initial.update(draft["payload"].get("fields", {}))
        initial["retain_images"] = draft["payload"].get("retain_images", True)
    form = ListingForm(request.POST if request.method == "POST" else None, request.FILES or None, initial=initial)
    status = 200
    if request.method == "POST":
        if request.user.status != "active":
            raise PermissionDenied("Restricted sellers can read history but cannot edit listings.")
        throttle("listing", request.user.pk)
        try:
            if request.META.get("CONTENT_LENGTH") and int(request.META["CONTENT_LENGTH"]) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
                raise ValidationError("The upload request exceeds 32 MiB.")
            expected = int(request.POST.get("expected_revision", ""))
            version = int(request.POST.get("draft_version", ""))
            if expected < 0 or version < 0:
                raise ValueError
            action = "publish" if force_publish else request.POST.get("action", "draft")
            options = {"product_id": product_id, "expected_revision": expected, "draft_version": version,
                       "retain_images": request.POST.get("retain_images") in ("on", "true", "1"),
                       "clear_draft_images": request.POST.get("clear_draft_images") in ("on", "true", "1")}
            if action == "draft":
                saved_id, _ = save_draft(request.user, request.POST, request.FILES.getlist("images"), **options)
                messages.success(request, "Draft saved privately. Your public revision has not changed.")
                return redirect("seller_edit", product_id=saved_id)
            if action != "publish":
                raise ValidationError("Choose a valid listing action.")
            if form.is_valid():
                saved_id, revision = publish_listing(request.user, form.cleaned_data, request.FILES.getlist("images"), **options)
                messages.success(request, f"Revision r{revision} submitted for scanning. Public access waits for a current successful assessment.")
                return redirect("seller_revisions", product_id=saved_id)
        except (ValueError, TypeError):
            form.add_error(None, "The form version is missing or invalid. Reload this page.")
            status = 409
        except ListingConflict as exc:
            form.add_error(None, str(exc))
            status = 409
        except ValidationError as exc:
            form.add_error(None, exc)
            status = 400
        except (DatabaseError, OSError):
            form.add_error(None, "The listing could not be saved. Your submitted text remains here. Reload if the listing changed.")
            status = 409
    images = rows("SELECT * FROM product_images WHERE product_id=%s AND revision_no=%s ORDER BY sort_order",
                  [product_id, product["current_revision_no"]]) if product else []
    return render(request, "seller/edit.html", {"title": f"Edit listing #{product_id}" if product else "Create listing",
        "form": form, "product": product, "locked": locked, "images": images, "draft": draft,
        "draft_images": draft["payload"].get("images", []) if draft else [],
        "currency": one("SELECT currency FROM marketplace_settings WHERE singleton")["currency"],
        "media_url": settings.MEDIA_URL, "locations": settings.DEMO_LOCATIONS}, status=status)


@require_role("seller")
def revisions(request, product_id, revision_no=None):
    product = _owned(request.user, product_id)
    revision_rows = rows("""SELECT r.*,(SELECT count(*) FROM product_images i WHERE
        (i.product_id,i.revision_no)=(r.product_id,r.revision_no)) AS image_count
        FROM product_revisions r WHERE r.product_id=%s ORDER BY r.revision_no DESC""", [product_id])
    selected = next((revision for revision in revision_rows if revision["revision_no"] == revision_no), None) if revision_no else None
    if revision_no is not None and selected is None:
        raise Http404
    jobs = rows("""SELECT j.job_id,j.revision_no,j.context_version,j.model_id,j.ruleset_id,j.status,j.attempts,
        j.feature_as_of,j.error_code,j.retry_at,l.risk_score,l.risk_level,l.predicted_at,l.observed_factors FROM risk_scan_jobs j
        LEFT JOIN risk_logs l USING(job_id) WHERE j.product_id=%s ORDER BY j.job_id DESC""", [product_id])
    images = rows("SELECT * FROM product_images WHERE product_id=%s AND revision_no=%s ORDER BY sort_order",
                  [product_id, revision_no]) if selected else []
    return render(request, "seller/revisions.html", {"title": f"Listing #{product_id} history", "product": product,
        "revisions": revision_rows, "selected": selected, "jobs": jobs, "images": images, "media_url": settings.MEDIA_URL})


@require_role("seller")
@require_POST
def withdraw(request, product_id):
    throttle("listing", request.user.pk)
    try:
        withdraw_listing(request.user, product_id)
    except ListingConflict as exc:
        return render(request, "seller/conflict.html", {"title": "Listing changed", "explanation": str(exc)}, status=409)
    messages.success(request, "Listing withdrawn. Its revisions and order history are retained.")
    return redirect("seller_dashboard")


@require_role("seller")
def draft_image(request, product_id, position):
    _owned(request.user, product_id)
    draft = one("SELECT payload FROM app_listing_drafts WHERE product_id=%s AND seller_id=%s", [product_id, request.user.pk])
    images = draft["payload"].get("images", []) if draft else []
    if not 0 <= position < len(images):
        raise Http404
    image = images[position]
    try:
        response = FileResponse(_path(image["storage_key"], private=True).open("rb"), content_type=image["content_type"])
    except FileNotFoundError as exc:
        raise Http404("Draft image unavailable.") from exc
    response["Cache-Control"] = "private, no-store"
    return response


@require_role("seller")
def assessment(request, product_id):
    product = _owned(request.user, product_id)
    if request.GET.get("format") == "fragment":
        response = render(request, "seller/risk_content.html", {"product": product})
    else:
        response = JsonResponse(one("SELECT * FROM current_listing_risk WHERE product_id=%s", [product_id]))
    response["Cache-Control"] = "private, no-store"
    return response
