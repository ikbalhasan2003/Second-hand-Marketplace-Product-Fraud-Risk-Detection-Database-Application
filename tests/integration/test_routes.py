"""Canonical marketplace routes and safe compatibility behavior."""
import pytest
from django.test import Client
from .test_accounts import member, PASSWORD
from .test_buyer import market  # noqa: F401

pytestmark = pytest.mark.django_db


def test_public_entry_and_legacy_bookmarks(client):
    assert client.get("/").status_code == 200
    assert client.get("/login/").status_code == 200
    assert client.get("/register/").status_code == 200
    for old, new in [("/buyer-app/", "/"), ("/seller-app/", "/sell/"),
                     ("/buyer-app/orders/42/", "/orders/42/"),
                     ("/seller-app/conversations/42/", "/sell/conversations/42/"),
                     ("/seller-app/login/", "/login/")]:
        assert client.get(old + "?page=2").url == new + "?page=2"
    assert client.get("/buyer-app///example.com/").status_code == 404
    assert client.get("/admin-app/").url == "/admin-app/login/?next=/admin-app/"
    assert client.get("/orders/42/").url == "/login/?next=/orders/42/"
    assert client.get("/sell/listings/42/edit/").url == "/login/?next=/sell/listings/42/edit/"
    assert client.get("/admin-app/register/").status_code == 404


@pytest.mark.parametrize("target", ["https://evil.invalid/", "//evil.invalid/", "///evil.invalid/", "http://testserver/orders/"])
def test_shared_login_rejects_unsafe_next(client, target):
    user = member()
    response = client.post("/login/", {"email": user.email, "password": PASSWORD}, QUERY_STRING="next=" + target, secure=True)
    assert response.url == "/"


def test_shared_login_roles_and_deep_link(client):
    seller = member(role="seller")
    assert client.post("/login/", {"email": seller.email, "password": PASSWORD}).url == "/sell/"
    assert client.get("/sell/").status_code == 200
    assert client.get("/orders/").status_code == 403
    assert client.get("/admin-app/").status_code == 403
    client.logout()
    buyer = member("buyer2@example.invalid")
    assert client.post("/login/?next=/orders/", {"email": buyer.email, "password": PASSWORD}).url == "/orders/"
    assert client.get("/sell/listings/1/edit/").status_code == 403
    client.logout()
    admin = member("admin2@example.invalid", "administrator")
    assert client.post("/login/", {"email": admin.email, "password": PASSWORD}).status_code == 200
    assert client.post("/admin-app/login/", {"email": admin.email, "password": PASSWORD}).url == "/admin-app/"
    assert client.get("/admin-app/").status_code == 200


def test_legacy_mutation_executes_once_without_redirect(client, market):  # noqa: F811
    client.force_login(market["buyer"])
    response = client.post(f"/buyer-app/listings/{market['product']}/conversations/")
    assert response.status_code == 302
    assert response.url.startswith("/conversations/")
    assert client.get(response.url).status_code == 200
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(market["buyer"])
    assert strict.post(f"/buyer-app/listings/{market['product']}/conversations/").status_code == 403


def test_registration_cannot_select_admin(client):
    assert client.post("/register/", {"role": "administrator"}).status_code == 403
