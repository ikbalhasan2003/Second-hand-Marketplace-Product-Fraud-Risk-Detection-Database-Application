import uuid
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from accounts.access import has_role, require_role
from accounts.throttle import throttle
from marketplace.db import actor_transaction, one, rows
from marketplace.services.orders import place_order, review_state, transition_order
from .forms import ReportForm, SearchForm


def fail(request, error, template, context):
    context["error"] = "; ".join(error.messages) if isinstance(error, ValidationError) else "The record changed or this action is not allowed. Review the current state and try again."
    return render(request, template, context, status=409)


def listing_record(product_id, revision=None):
    return one("""SELECT p.*,r.*,u.full_name AS seller_name,u.created_at AS seller_joined,
        c.name AS category_name,u.status AS seller_status,u.is_active AS seller_auth_active,
        k.assessment_state,k.risk_score,k.risk_level,k.feature_as_of,k.predicted_at,k.risk_id
        FROM products p JOIN product_revisions r ON r.product_id=p.product_id AND r.revision_no=coalesce(%s,p.current_revision_no)
        JOIN users u ON u.user_id=p.seller_id JOIN categories c USING(category_id)
        LEFT JOIN current_listing_risk k ON k.product_id=p.product_id WHERE p.product_id=%s""", [revision, product_id])


def catalog(request):
    form = SearchForm(request.GET)
    form.fields["category"].choices += [(str(row["category_id"]), row["name"]) for row in rows("SELECT category_id,name FROM categories ORDER BY name")]
    where = ["p.visibility='visible'", "p.availability IN ('available','reserved','sold')", "u.status='active'", "u.is_active"]
    params = []
    data = form.cleaned_data if form.is_valid() else {}
    if form.is_valid():
        if data.get("q"):
            where.append("to_tsvector('simple',r.title || ' ' || r.description) @@ plainto_tsquery('simple',%s)")
            params.append(data["q"])
        for field, expression in [("category", "r.category_id=%s"), ("minimum", "r.price>=%s"), ("maximum", "r.price<=%s"), ("condition", "r.condition=%s"), ("location", "lower(r.location)=lower(%s)")]:
            if data.get(field) is not None and data.get(field) != "":
                where.append(expression)
                params.append(data[field])
        if data.get("risk"):
            # A completed current assessment has a unique bound job. Test that
            # indexed relation directly; evaluating the display view for every
            # catalog candidate causes needless lateral job scans.
            ready = """EXISTS(SELECT 1 FROM risk_scan_jobs j JOIN risk_logs l USING(job_id)
                JOIN risk_models m ON m.model_id=j.model_id AND m.state='active'
                JOIN risk_rulesets s ON s.ruleset_id=j.ruleset_id AND s.state='active'
                WHERE j.product_id=p.product_id AND j.revision_no=p.current_revision_no
                AND j.context_version=p.context_version AND j.status='succeeded'
                AND j.feature_schema_id=m.feature_schema_id AND j.feature_schema_id=s.feature_schema_id
                AND j.feature_as_of>=clock_timestamp()-s.max_assessment_age
                AND j.feature_as_of<=clock_timestamp()"""
            if data["risk"] == "unassessed":
                where.append("NOT " + ready + ")")
            else:
                where.append(ready + " AND l.risk_level=%s)")
                params.append(data["risk"])
    else:
        where.append("false")
    join = """FROM products p JOIN product_revisions r ON (r.product_id,r.revision_no)=(p.product_id,p.current_revision_no)
        JOIN users u ON u.user_id=p.seller_id WHERE """ + " AND ".join(where)
    count = one("SELECT count(*) AS total " + join, params)["total"]
    page = Paginator(range(count), 12).get_page(request.GET.get("page"))
    sort = "r.price,p.product_id DESC" if data.get("sort") == "price" else "p.created_at DESC,p.product_id DESC"
    listings = rows("SELECT p.product_id,p.availability,r.title,r.price,r.currency,r.location,u.full_name AS seller_name,u.created_at AS seller_joined,(SELECT storage_key FROM product_images i WHERE i.product_id=p.product_id AND i.revision_no=p.current_revision_no ORDER BY sort_order LIMIT 1) AS image_key " + join + " ORDER BY " + sort + " LIMIT 12 OFFSET %s", params + [(page.number - 1) * 12])
    risk_by_product = {item["product_id"]: item for item in rows("SELECT product_id,assessment_state,risk_level FROM current_listing_risk WHERE product_id=ANY(%s)", [[item["product_id"] for item in listings]])} if listings else {}
    for listing in listings:
        listing.update(risk_by_product.get(listing["product_id"], {"assessment_state": "pending", "risk_level": None}))
    if data.get("risk") in ("low", "medium", "high"):
        listings = [item for item in listings if item["assessment_state"] == "ready" and item["risk_level"] == data["risk"]]
    elif data.get("risk") == "unassessed":
        listings = [item for item in listings if item["assessment_state"] != "ready"]
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "buyer/catalog.html", {"title": "Browse listings", "form": form, "listings": listings, "page": page, "query": query.urlencode(), "count": count, "filtered": any(value for key, value in request.GET.items() if key != "page")})


def listing_detail(request, product_id, revision_no=None):
    listing = listing_record(product_id, revision_no)
    if not listing:
        raise Http404
    public = listing["visibility"] == "visible" and listing["availability"] != "draft" and listing["seller_status"] == "active" and listing["seller_auth_active"]
    if revision_no or not public:
        permitted = request.user.is_authenticated and (request.user.pk == listing["seller_id"] or has_role(request.user, "administrator") or
            one("SELECT 1 FROM transactions WHERE product_id=%s AND buyer_id=%s AND revision_no=%s", [product_id, request.user.pk, listing["revision_no"]]) or
            one("SELECT 1 FROM fraud_reports WHERE product_id=%s AND reporter_id=%s AND revision_no=%s", [product_id, request.user.pk, listing["revision_no"]]))
        if not permitted:
            raise Http404
    images = rows("SELECT * FROM product_images WHERE product_id=%s AND revision_no=%s ORDER BY sort_order", [product_id, listing["revision_no"]])
    assessment = one("""SELECT h.observed_factors,m.version AS model_version,s.version AS ruleset_version
        FROM risk_score_history h JOIN current_listing_risk k USING(risk_id)
        JOIN risk_models m ON m.model_id=h.model_id JOIN risk_rulesets s ON s.ruleset_id=h.ruleset_id
        WHERE k.product_id=%s AND k.assessment_state='ready'""", [product_id]) if revision_no is None else None
    context = {"title": listing["title"], "listing": listing, "images": images, "assessment": assessment, "request_key": uuid.uuid4(), "historical": revision_no is not None}
    context["review_token"] = signing.dumps([product_id, listing["revision_no"], review_state(listing)], salt="order-review")
    context["revisions"] = rows("SELECT revision_no,created_at FROM product_revisions WHERE product_id=%s ORDER BY revision_no DESC", [product_id]) if request.user.is_authenticated and request.user.pk == listing["seller_id"] else []
    if request.GET.get("assessment") == "fragment":
        response = render(request, "components/risk.html", context)
        response["Cache-Control"] = "private, no-store"
        return response
    return render(request, "buyer/detail.html", context)


@require_role("buyer", active=True)
@require_POST
def purchase(request, product_id):
    try:
        order_id = place_order(request.user, product_id, int(request.POST.get("revision_no", "0")), request.POST.get("request_key"), request.POST.get("acknowledge") == "yes", request.POST.get("review_token"))
    except (DatabaseError, ValidationError, ValueError) as error:
        return fail(request, error, "buyer/conflict.html", {"title": "Purchase needs review", "product_id": product_id, "purchase_retry": request.POST})
    return redirect(f"/buyer-app/orders/{order_id}/")


def role_gate(request, role):
    if role not in ("buyer", "seller") or not has_role(request.user, role):
        raise PermissionDenied


def orders(request, role="buyer"):
    role_gate(request, role)
    column = "buyer_id" if role == "buyer" else "seller_id"
    state = request.GET.get("status", "")
    suffix, params = column + "=%s", [request.user.pk]
    if state:
        suffix += " AND status=%s"
        params.append(state)
    count = one("SELECT count(*) AS n FROM seller_order_history WHERE " + suffix, params)["n"]
    page = Paginator(range(count), 20).get_page(request.GET.get("page"))
    result = rows("SELECT h.*,(SELECT full_name FROM users WHERE user_id=h.buyer_id) AS buyer_name,(SELECT full_name FROM users WHERE user_id=h.seller_id) AS seller_name FROM seller_order_history h WHERE " + suffix + " ORDER BY created_at DESC,transaction_id DESC LIMIT 20 OFFSET %s", params + [(page.number - 1) * 20])
    return render(request, "buyer/orders.html", {"title": "My purchases" if role == "buyer" else "Sales", "orders": result, "role": role, "page": page, "query": "status=" + state, "states": ("placed", "accepted", "shipped", "disputed", "completed", "cancelled")})


def order_detail(request, order_id, role="buyer"):
    role_gate(request, role)
    column = "buyer_id" if role == "buyer" else "seller_id"
    order = one("SELECT * FROM seller_order_history WHERE transaction_id=%s AND " + column + "=%s", [order_id, request.user.pk])
    if not order:
        raise Http404
    events = rows("SELECT * FROM order_status_history WHERE transaction_id=%s ORDER BY event_id", [order_id])
    context = {"title": f"Order #{order_id}", "order": order, "events": events, "role": role}
    if request.method == "POST":
        try:
            transition_order(request.user, order_id, request.POST.get("status"), request.POST.get("reason", ""), request.POST.get("expected_status"))
        except (DatabaseError, ValidationError) as error:
            return fail(request, error, "buyer/order.html", context)
        messages.success(request, "Order updated with a retained history event.")
        return redirect(f"/{role}-app/orders/{order_id}/")
    return render(request, "buyer/order.html", context)


@require_role("buyer", active=True)
@require_POST
def start_conversation(request, product_id):
    listing = listing_record(product_id)
    if not listing or listing["visibility"] != "visible" or listing["availability"] == "draft" or listing["seller_id"] == request.user.pk:
        raise Http404
    with actor_transaction(request.user):
        conversation = one("INSERT INTO conversations(product_id,buyer_id) VALUES(%s,%s) ON CONFLICT(product_id,buyer_id) DO NOTHING RETURNING conversation_id", [product_id, request.user.pk])
        conversation = conversation or one("SELECT conversation_id FROM conversations WHERE product_id=%s AND buyer_id=%s", [product_id, request.user.pk])
    return redirect(f"/buyer-app/conversations/{conversation['conversation_id']}/")


def conversation_record(request, conversation_id, role):
    role_gate(request, role)
    record = one("""SELECT c.*,p.seller_id,r.title FROM conversations c JOIN products p USING(product_id)
        JOIN product_revisions r ON (r.product_id,r.revision_no)=(p.product_id,p.current_revision_no)
        WHERE c.conversation_id=%s AND (c.buyer_id=%s OR p.seller_id=%s)""", [conversation_id, request.user.pk, request.user.pk])
    if not record or (role == "buyer" and record["buyer_id"] != request.user.pk) or (role == "seller" and record["seller_id"] != request.user.pk):
        raise Http404
    return record


def conversations(request, role="buyer"):
    role_gate(request, role)
    column = "c.buyer_id" if role == "buyer" else "p.seller_id"
    count = one("SELECT count(*) AS n FROM conversations c JOIN products p USING(product_id) WHERE " + column + "=%s", [request.user.pk])["n"]
    page = Paginator(range(count), 20).get_page(request.GET.get("page"))
    result = rows("""SELECT c.*,r.title FROM conversations c JOIN products p USING(product_id)
        JOIN product_revisions r ON (r.product_id,r.revision_no)=(p.product_id,p.current_revision_no)
        WHERE """ + column + "=%s ORDER BY c.conversation_id DESC LIMIT 20 OFFSET %s", [request.user.pk, (page.number - 1) * 20])
    return render(request, "buyer/conversations.html", {"title": "Messages", "conversations": result, "role": role, "page": page})


def conversation_detail(request, conversation_id, role="buyer"):
    conversation = conversation_record(request, conversation_id, role)
    history = rows("SELECT message_id,sender_id,message_text,sent_at,read_at FROM chat_messages WHERE conversation_id=%s ORDER BY message_id DESC LIMIT 50", [conversation_id])
    context = {"title": conversation["title"], "conversation": conversation, "role": role, "history": list(reversed(history)), "has_older": len(history) == 50}
    if request.method == "POST":
        if request.user.status != "active":
            raise PermissionDenied
        text = request.POST.get("message", "").strip()
        if not 1 <= len(text) <= 4000:
            context["error"] = "Enter a message of 1 to 4000 characters."
        else:
            throttle("message", request.user.pk)
            with actor_transaction(request.user):
                rows("INSERT INTO chat_messages(conversation_id,sender_id,message_text) VALUES(%s,%s,%s)", [conversation_id, request.user.pk, text])
            messages.success(request, "Message sent.")
            return redirect(f"/{role}-app/conversations/{conversation_id}/")
    return render(request, "buyer/conversation.html", context)


def poll_messages(request, conversation_id, role="buyer"):
    conversation_record(request, conversation_id, role)
    try:
        after = max(0, int(request.GET.get("after_id", "0")))
        before = max(0, int(request.GET.get("before_id", "0")))
        if max(after, before) > 2**63 - 1:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "Invalid message cursor"}, status=400)
    if before:
        result = list(reversed(rows("SELECT message_id,sender_id,message_text,sent_at,read_at FROM chat_messages WHERE conversation_id=%s AND message_id<%s ORDER BY message_id DESC LIMIT 50", [conversation_id, before])))
    else:
        result = rows("SELECT message_id,sender_id,message_text,sent_at,read_at FROM chat_messages WHERE conversation_id=%s AND message_id>%s ORDER BY message_id LIMIT 50", [conversation_id, after])
    receipts = rows("SELECT message_id,read_at FROM chat_messages WHERE conversation_id=%s AND sender_id=%s AND read_at IS NOT NULL ORDER BY message_id DESC LIMIT 50", [conversation_id, request.user.pk])
    return JsonResponse({"messages": result, "receipts": receipts, "has_more": len(result) == 50})


@require_POST
def mark_read(request, conversation_id, role="buyer"):
    conversation_record(request, conversation_id, role)
    try:
        through = max(0, int(request.POST.get("through_id", "0")))
        if through > 2**63 - 1:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "Invalid message cursor"}, status=400)
    with actor_transaction(request.user):
        if "message_ids" in request.POST:
            try:
                ids = [int(value) for value in request.POST.get("message_ids", "").split(",") if value]
                if len(ids) > 50 or any(not 0 < value <= 2**63 - 1 for value in ids):
                    raise ValueError
            except ValueError:
                return JsonResponse({"error": "Invalid visible message IDs"}, status=400)
            rows("UPDATE chat_messages SET read_at=clock_timestamp() WHERE conversation_id=%s AND message_id=ANY(%s) AND sender_id<>%s AND read_at IS NULL", [conversation_id, ids, request.user.pk])
        else:
            rows("UPDATE chat_messages SET read_at=clock_timestamp() WHERE conversation_id=%s AND message_id<=%s AND sender_id<>%s AND read_at IS NULL", [conversation_id, through, request.user.pk])
    return JsonResponse({"read": True})


@require_role("buyer", active=True)
def report_new(request, product_id):
    listing = listing_record(product_id)
    order_reference = request.POST.get("order_id") if request.method == "POST" else request.GET.get("order")
    if not listing or listing["seller_id"] == request.user.pk:
        raise Http404
    initial = {"revision_no": listing["revision_no"], "order_id": order_reference}
    if order_reference:
        try:
            order_id = int(order_reference)
        except (ValueError, TypeError) as exc:
            raise Http404 from exc
        order = one("SELECT revision_no FROM transactions WHERE transaction_id=%s AND product_id=%s AND buyer_id=%s", [order_id, product_id, request.user.pk])
        if not order:
            raise Http404
        initial["revision_no"] = order["revision_no"]
        listing = listing_record(product_id, order["revision_no"])
    elif listing["visibility"] != "visible" or listing["availability"] == "draft":
        raise Http404
    form = ReportForm(request.POST or None, initial=initial)
    context = {"title": "Report a concern", "listing": listing, "form": form}
    if request.method == "POST" and form.is_valid():
        from marketplace.uploads import validate_image, store_image, remove_stored
        stored = []
        try:
            files = request.FILES.getlist("evidence")
            if len(files) > 3:
                raise ValidationError("At most three evidence images are allowed.")
            validated = [validate_image(file) for file in files]
            throttle("report", request.user.pk)
            data = form.cleaned_data
            with actor_transaction(request.user, "Member submitted concern"):
                target = one("SELECT * FROM products WHERE product_id=%s FOR UPDATE", [product_id])
                if data["order_id"]:
                    order = one("SELECT revision_no FROM transactions WHERE transaction_id=%s AND product_id=%s AND buyer_id=%s", [data["order_id"], product_id, request.user.pk])
                    if not order or order["revision_no"] != data["revision_no"]:
                        raise ValidationError("The order does not match this report revision.")
                elif data["revision_no"] != target["current_revision_no"]:
                    raise ValidationError("Listing changed. Review the latest revision before submitting.")
                report = one("INSERT INTO fraud_reports(product_id,revision_no,reporter_id,transaction_id,reason_code,comment) VALUES(%s,%s,%s,%s,%s,%s) RETURNING report_id", [product_id, data["revision_no"], request.user.pk, data["order_id"], data["reason_code"], data["comment"]])
                for index, image in enumerate(validated):
                    metadata = store_image(image, private=True)
                    stored.append(metadata)
                    rows("INSERT INTO report_attachments(report_id,storage_key,sort_order,content_type,byte_size,content_sha256) VALUES(%s,%s,%s,%s,%s,%s)", [report["report_id"], metadata["storage_key"], index, metadata["content_type"], metadata["byte_size"], metadata["content_sha256"]])
            messages.success(request, "Concern submitted. Evidence is private to you and authorized administrators.")
            return redirect(f"/buyer-app/reports/{report['report_id']}/")
        except (DatabaseError, ValidationError, OSError) as error:
            for metadata in stored:
                try:
                    remove_stored(metadata, private=True)
                except OSError:
                    pass  # Private, unreferenced rollback file; reference-aware maintenance may retry.
            return fail(request, error, "buyer/report_form.html", context)
    return render(request, "buyer/report_form.html", context)


@require_role("buyer")
def reports(request):
    state = request.GET.get("status", "")
    suffix, params = "reporter_id=%s", [request.user.pk]
    if state:
        suffix += " AND status=%s"
        params.append(state)
    count = one("SELECT count(*) AS n FROM fraud_reports WHERE " + suffix, params)["n"]
    page = Paginator(range(count), 20).get_page(request.GET.get("page"))
    result = rows("SELECT f.*,r.title FROM fraud_reports f JOIN product_revisions r USING(product_id,revision_no) WHERE " + suffix + " ORDER BY report_id DESC LIMIT 20 OFFSET %s", params + [(page.number - 1) * 20])
    return render(request, "buyer/reports.html", {"title": "My submitted reports", "reports": result, "page": page, "query": "status=" + state, "states": ("pending", "reviewing", "resolved", "dismissed")})


@require_role("buyer")
def report_detail(request, report_id):
    report = one("SELECT * FROM fraud_reports WHERE report_id=%s AND reporter_id=%s", [report_id, request.user.pk])
    if not report:
        raise Http404
    attachments = rows("SELECT attachment_id,content_type,byte_size FROM report_attachments WHERE report_id=%s ORDER BY sort_order", [report_id])
    return render(request, "buyer/report.html", {"title": f"Report #{report_id}", "report": report, "attachments": attachments, "evidence_remaining": 3 - len(attachments)})


@require_role("buyer")
@require_POST
def append_evidence(request, report_id):
    """Existing open cases remain usable after marketplace blocking/deactivation."""
    from marketplace.uploads import validate_image, store_image, remove_stored
    report = one("SELECT * FROM fraud_reports WHERE report_id=%s AND reporter_id=%s", [report_id, request.user.pk])
    if not report:
        raise Http404
    written = []
    try:
        files = request.FILES.getlist("evidence")
        if not 1 <= len(files) <= 3:
            raise ValidationError("Select one to three evidence images; each case may have at most three total.")
        validated = [validate_image(file) for file in files]
        throttle("report", request.user.pk)
        with actor_transaction(request.user, "Reporter appended existing-case evidence"):
            user = one("SELECT is_active FROM users WHERE user_id=%s FOR UPDATE", [request.user.pk])
            if not user or not user["is_active"]:
                raise PermissionDenied
            rows("SELECT product_id FROM products WHERE product_id=%s FOR UPDATE", [report["product_id"]])
            current = one("SELECT * FROM fraud_reports WHERE report_id=%s AND reporter_id=%s FOR UPDATE", [report_id, request.user.pk])
            if not current or current["status"] not in ("pending", "reviewing"):
                raise ValidationError("Evidence can be added only while your case is open.")
            existing = rows("SELECT sort_order FROM report_attachments WHERE report_id=%s ORDER BY sort_order", [report_id])
            if len(existing) + len(validated) > 3:
                raise ValidationError("This case may have at most three evidence images in total.")
            for index, image in enumerate(validated, start=len(existing)):
                metadata = store_image(image, private=True)
                written.append(metadata)
                rows("""INSERT INTO report_attachments(report_id,storage_key,sort_order,content_type,byte_size,content_sha256)
                    VALUES(%s,%s,%s,%s,%s,%s)""", [report_id, metadata["storage_key"], index, metadata["content_type"],
                    metadata["byte_size"], metadata["content_sha256"]])
        messages.success(request, "Private evidence added to your existing case.")
        return redirect(f"/buyer-app/reports/{report_id}/")
    except (ValidationError, DatabaseError, OSError) as error:
        for metadata in written:
            try:
                remove_stored(metadata, private=True)
            except OSError:
                pass
        attachments = rows("SELECT attachment_id,content_type,byte_size FROM report_attachments WHERE report_id=%s ORDER BY sort_order", [report_id])
        return fail(request, error, "buyer/report.html", {"title": f"Report #{report_id}", "report": report, "attachments": attachments, "evidence_remaining": 3 - len(attachments)})


def evidence(request, attachment_id):
    if not request.user.is_authenticated:
        raise PermissionDenied
    attachment = one("SELECT a.*,f.reporter_id FROM report_attachments a JOIN fraud_reports f USING(report_id) WHERE attachment_id=%s", [attachment_id])
    if not attachment or (attachment["reporter_id"] != request.user.pk and not (has_role(request.user, "administrator") and request.user.status == "active")):
        raise Http404
    root = settings.PRIVATE_MEDIA_ROOT.resolve()
    path = (root / attachment["storage_key"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise Http404
    response = FileResponse(path.open("rb"), content_type=attachment["content_type"])
    response["Cache-Control"] = "private, no-store"
    response["Content-Disposition"] = 'inline; filename="evidence' + path.suffix + '"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
