"""UI contracts over real persisted marketplace state; optional Edge layout checks."""
from pathlib import Path
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.core import signing
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import Client

from accounts.models import User
from marketplace.db import actor_transaction, one, rows
from marketplace.services.listings import publish_listing
from marketplace.services.orders import place_order, review_state


@pytest.fixture
def interface_market(db):
    people = {}
    for role in ("buyer", "seller", "administrator"):
        user = User.objects.create_user(f"ui-{role}@example.invalid", full_name=f"UI {role}")
        user.groups.add(Group.objects.get(name=role))
        people[role] = user
    product, _ = publish_listing(people["seller"], {
        "title": "Interface telescope", "description": "Recorded description for interface verification.",
        "category_id": one("SELECT category_id FROM categories LIMIT 1")["category_id"],
        "price": 80, "condition": "good", "location": "Shanghai",
    })
    people["product"] = product
    return people


@pytest.mark.parametrize("state,label", [
    ("pending", "Scan pending"), ("scanning", "Scanning"), ("failed", "Scan failed"),
    ("stale", "Unassessed"), (None, "Unassessed"),
])
def test_unfinished_assessments_never_display_an_old_score(state, label):
    html = render_to_string("components/risk.html", {"listing": {
        "assessment_state": state, "risk_score": 99, "risk_level": "high", "current_revision_no": 2,
    }})
    assert label in html
    assert "99/100" not in html
    assert "High risk" not in html


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_current_risk_labels_and_real_scores(level):
    html = render_to_string("components/risk.html", {"listing": {
        "assessment_state": "ready", "risk_score": 42, "risk_level": level, "current_revision_no": 3,
    }})
    assert f"{level.title()} risk" in html
    assert "Risk score: 42/100" in html
    assert "Assessed revision r3" in html
    assert "not a fraud verdict" in html


def test_bound_forms_categories_medium_filter_and_error_summary(client, interface_market):
    response = client.get("/buyer-app/listings/", {"minimum": 100, "maximum": 10})
    assert b'data-error-summary' in response.content
    assert b'for="id_minimum"' in response.content
    assert b'value="100"' in response.content
    assert b'Current medium risk' in response.content
    assert b'All categories' in response.content
    assert client.get("/buyer-app/listings/", {"risk": "medium"}).context["count"] == 0


def test_review_rejects_changed_assessment_and_reconciles_committed_request(client, interface_market):
    market = interface_market
    client.force_login(market["buyer"])
    endpoint = f"/buyer-app/listings/{market['product']}/"
    page = client.get(endpoint)
    assert b'data-order-review' in page.content
    assert b'Payment and refunds take place outside this app' in page.content
    key = uuid4()
    bad_token = signing.dumps([market["product"], 1, ["ready", "low", "0"]], salt="order-review")
    payload = {"revision_no": 1, "request_key": key, "review_token": bad_token}
    conflict = client.post(endpoint + "orders/", payload)
    assert conflict.status_code == 409
    assert str(key).encode() in conflict.content
    assert one("SELECT count(*) AS n FROM transactions")["n"] == 0
    risk = one("SELECT * FROM current_listing_risk WHERE product_id=%s", [market["product"]])
    token = signing.dumps([market["product"], 1, review_state(risk)], salt="order-review")
    order = place_order(market["buyer"], market["product"], 1, key, review_token=token)
    assert place_order(market["buyer"], market["product"], 1, key, review_token=token) == order
    with pytest.raises(ValidationError):
        place_order(market["buyer"], market["product"], 2, key, review_token=token)


def test_readable_chat_without_javascript_and_private_risk_fragments(client, interface_market):
    market = interface_market
    client.force_login(market["buyer"])
    conversation = client.post(f"/buyer-app/listings/{market['product']}/conversations/").url
    client.post(conversation, {"message": "Preserve this actual message"})
    assert b'Preserve this actual message' in client.get(conversation).content
    fragment = client.get(f"/buyer-app/listings/{market['product']}/?assessment=fragment")
    assert fragment.status_code == 200 and "no-store" in fragment["Cache-Control"]
    assert b'<html' not in fragment.content
    with actor_transaction(market["administrator"], "Restrict synthetic UI member"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [market["buyer"].pk])
    restricted = client.get(conversation)
    assert b'Account restricted' in restricted.content
    assert b'<textarea' not in restricted.content
    assert b'Preserve this actual message' in restricted.content


def test_assignment_rescan_receipts_and_filtered_histories(client, interface_market):
    market = interface_market
    client.force_login(market["buyer"])
    client.post(f"/buyer-app/listings/{market['product']}/reports/", {"revision_no": 1, "reason_code": "other", "comment": "Synthetic interface concern"})
    report = one("SELECT report_id FROM fraud_reports WHERE product_id=%s", [market["product"]])["report_id"]
    assert client.get("/buyer-app/reports/?status=resolved").context["page"].paginator.count == 0
    client.force_login(market["administrator"])
    case_url = f"/admin-app/cases/{market['product']}/"
    assignment = {"operation": "assign", "report_id": report, "expected_status": "pending", "assign_to_me": "yes", "reason": "Claim synthetic concern for review"}
    assigned = client.post(case_url, assignment)
    assert assigned.status_code == 302 and "/audit-log/" in assigned.url
    assert one("SELECT assigned_admin_id FROM fraud_reports WHERE report_id=%s", [report])["assigned_admin_id"] == market["administrator"].pk
    assert client.post(case_url, assignment).status_code == 409
    assert client.get("/admin-app/review-queue/?unassigned=on").context["page"].paginator.count == 0
    assert client.get("/admin-app/review-queue/", {"assignee": market["administrator"].pk}).context["page"].paginator.count == 1
    request = {"product_id": market["product"], "request_key": str(uuid4()), "reason": "Reassess synthetic published listing"}
    first = client.post("/admin-app/", request)
    assert first.status_code == 302 and client.post("/admin-app/", request).url == first.url
    assert one("SELECT count(*) AS n FROM admin_audit_logs WHERE action_type='manual_rescan'")["n"] == 1
    audits = client.get("/admin-app/audit-log/", {"target_type": "report", "target_id": report})
    assert audits.context["page"].paginator.count >= 1


def test_all_17_page_groups_render_at_desktop_and_mobile(interface_market, settings):
    """Route browser requests through Django's test client and actual local assets.

    No live server or external services are used. Install browser-lock.txt for this check.
    """
    sync = pytest.importorskip("playwright.sync_api")
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if not edge.exists():
        pytest.skip("Microsoft Edge is not installed")
    market = interface_market
    buyer, seller, admin = (Client() for _ in range(3))
    buyer.force_login(market["buyer"])
    seller.force_login(market["seller"])
    admin.force_login(market["administrator"])
    product = market["product"]
    chat = buyer.post(f"/buyer-app/listings/{product}/conversations/").url
    conversation_id = int(chat.rstrip("/").split("/")[-1])
    with actor_transaction(market["seller"]):
        rows("INSERT INTO chat_messages(conversation_id,sender_id,message_text) SELECT %s,%s,'Synthetic UI message ' || n FROM generate_series(1,60) n", [conversation_id, market["seller"].pk])
    pages = [
        (buyer, "/buyer-app/listings/"), (buyer, f"/buyer-app/listings/{product}/"),
        (Client(), "/buyer-app/register/"), (buyer, "/buyer-app/orders/"),
        (buyer, chat), (buyer, f"/buyer-app/listings/{product}/reports/new/"),
        (buyer, "/buyer-app/reports/"), (seller, "/seller-app/"),
        (seller, "/seller-app/listings/new/"), (seller, f"/seller-app/listings/{product}/revisions/"),
        (seller, "/seller-app/orders/"), (seller, chat.replace("buyer-app", "seller-app")),
        (admin, "/admin-app/"), (admin, "/admin-app/review-queue/"),
        (admin, "/admin-app/models/"), (admin, "/admin-app/audit-log/"), (admin, "/admin-app/exports/"),
    ]
    # Render in the test's DB thread; browser callbacks serve the captured documents.
    documents = {path: client.get(path).content for client, path in pages}
    documents["/validation/"] = buyer.get("/buyer-app/listings/", {"minimum": 100, "maximum": 10}).content
    latest = one("SELECT max(message_id) AS n FROM chat_messages WHERE conversation_id=%s", [conversation_id])["n"]
    first_visible = buyer.get(chat).context["history"][0]["message_id"]
    older_payload = buyer.get(chat + f"messages/?before_id={first_visible}").json()
    with actor_transaction(market["seller"]):
        rows("INSERT INTO chat_messages(conversation_id,sender_id,message_text) VALUES(%s,%s,'Actual persisted incoming message')", [conversation_id, market["seller"].pk])
    incoming_payload = buyer.get(chat + f"messages/?after_id={latest}").json()
    with sync.sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=str(edge), headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def serve(route):
            from urllib.parse import urlsplit
            path = urlsplit(route.request.url).path
            if path.startswith("/static/"):
                file = settings.BASE_DIR / path.lstrip("/")
                route.fulfill(body=file.read_bytes(), content_type="text/css" if file.suffix == ".css" else "application/javascript")
            elif path in documents and route.request.resource_type == "document":
                route.fulfill(body=documents[path], content_type="text/html")
            else:
                route.fulfill(status=404, body="Unavailable")

        page.route("http://ui.test/**", serve)
        for width in (1440, 360):
            page.set_viewport_size({"width": width, "height": 900})
            for _, path in pages:
                page.goto("http://ui.test" + path)
                assert page.locator("h1").count() == 1, path
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, path)
                assert page.locator("input:not([type=hidden]):not([type=submit]),textarea,select").evaluate_all(
                    "fields => fields.every(field => field.labels.length || field.hasAttribute('aria-label'))"
                ), path
                if width == 360 and path in ("/buyer-app/listings/", "/admin-app/models/"):
                    directory = settings.BASE_DIR / ".local" / "ui-qa"
                    directory.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(directory / ("buyer-mobile.png" if "buyer-app" in path else "admin-mobile.png")), full_page=True)
        page.goto(f"http://ui.test/buyer-app/listings/{product}/")
        trigger = page.locator('[data-review-trigger]')
        trigger.focus()
        page.keyboard.press("Enter")
        assert page.locator("dialog").evaluate("dialog => dialog.matches(':modal')")
        page.keyboard.press("Escape")
        assert trigger.evaluate("element => element === document.activeElement")
        # A refresh error must preserve the draft, focus and scroll, never erase history.
        page.clock.install()
        page.goto("http://ui.test" + chat)
        draft = page.locator("#message")
        draft.fill("Unsent draft survives a polling failure")
        draft.focus()
        page.clock.fast_forward(6000)
        sync.expect(page.locator("#poll-status")).to_contain_text("Unable to refresh")
        assert draft.input_value() == "Unsent draft survives a polling failure"
        assert draft.evaluate("element => element === document.activeElement")
        list_region = page.locator('#messages')
        list_region.evaluate("list => list.scrollTop = 20")
        page.route('**/messages/?after_id=*', lambda route: route.fulfill(json=incoming_payload))
        page.clock.fast_forward(11000)
        sync.expect(list_region).to_contain_text('Actual persisted incoming message')
        assert list_region.evaluate('list => list.scrollTop') == 20
        page.clock.fast_forward(6000)
        assert list_region.locator('li').count() == 51  # repeated polling deduplicates IDs
        assert draft.input_value() == "Unsent draft survives a polling failure"
        assert draft.evaluate("element => element === document.activeElement")
        page.route('**/messages/?before_id=*', lambda route: route.fulfill(json=older_payload))
        page.get_by_role('button', name='Load earlier messages').click()
        sync.expect(list_region.locator('li')).to_have_count(61)
        page.reload()
        assert draft.input_value() == "Unsent draft survives a polling failure"
        # Risk refresh failures retain the last real state, including its no-score contract.
        page.goto(f"http://ui.test/buyer-app/listings/{product}/")
        page.clock.fast_forward(11000)
        sync.expect(page.locator('[data-risk-status]')).to_contain_text("Unable to refresh")
        assert "Scan pending" in page.locator('[data-risk-refresh]').inner_text()
        assert "/100" not in page.locator('[data-risk-refresh]').inner_text()
        # Focus may enter the panel after a request starts but before it completes.
        page.evaluate("""() => {
            window.fetch = () => new Promise(resolve => {window.finishRiskRefresh = resolve;});
            const region = document.querySelector('[data-risk-refresh]');
            window.riskResponse = region.innerHTML;
            const button = document.createElement('button');
            button.id = 'risk-focus-probe'; button.textContent = 'Panel action';
            region.append(button);
        }""")
        page.clock.fast_forward(21000)
        page.wait_for_function('window.finishRiskRefresh !== undefined')
        page.locator('#risk-focus-probe').focus()
        page.evaluate("window.finishRiskRefresh(new Response(window.riskResponse))")
        sync.expect(page.locator('#risk-focus-probe')).to_be_focused()
        page.goto("http://ui.test/validation/")
        assert page.locator('[data-error-summary]').evaluate("element => element === document.activeElement")
        assert page.locator('#id_minimum').get_attribute('aria-invalid') is None  # non-field range error
        page.goto(f"http://ui.test/buyer-app/listings/{product}/reports/new/")
        page.locator('#evidence').set_input_files({"name": "unsupported.svg", "mimeType": "image/svg+xml", "buffer": b"<svg/>"})
        assert not page.locator('#evidence').evaluate("input => input.checkValidity()")
        sync.expect(page.locator('.upload-preview')).to_contain_text("Unsupported image format")
        page.get_by_role('button', name='Remove unsupported.svg').click()
        assert page.locator('#evidence').evaluate("input => input.files.length") == 0
        assert not errors
        browser.close()
