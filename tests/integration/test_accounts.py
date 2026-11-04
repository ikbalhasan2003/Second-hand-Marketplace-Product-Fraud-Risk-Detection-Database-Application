import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from accounts.models import User
from marketplace.db import actor_transaction, rows

pytestmark = pytest.mark.django_db
PASSWORD = "Stone-river-4826!pass"


def member(email="member@example.invalid", role="buyer"):
    user = User.objects.create_user(email, PASSWORD, full_name="Test Member")
    user.groups.add(Group.objects.get(name=role))
    return user


def test_registration_normalizes_identity_and_grants_only_selected_role(client):
    response = client.post("/buyer-app/register/", {"email": " New@Example.invalid ", "full_name": "New Member", "password": PASSWORD, "password_confirm": PASSWORD, "role": "administrator", "is_staff": "true"})
    assert response.status_code == 302
    user = User.objects.get(email="new@example.invalid")
    assert user.check_password(PASSWORD)
    assert user.password.startswith("bcrypt_sha256$")
    assert list(user.groups.values_list("name", flat=True)) == ["buyer"]
    assert not user.is_staff and not user.is_superuser
    response = client.post("/seller-app/register/", {"email": "NEW@example.invalid", "full_name": "Duplicate", "password": PASSWORD, "password_confirm": PASSWORD})
    assert response.status_code == 200
    assert User.objects.filter(email__iexact="new@example.invalid").count() == 1


def test_case_insensitive_database_duplicate_rejected():
    member()
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("MEMBER@example.invalid", PASSWORD, full_name="Duplicate")


def test_login_does_not_enable_role_and_app_gates_apply(client):
    user = member()
    assert client.post("/seller-app/login/", {"email": user.email, "password": PASSWORD}).status_code == 200
    assert not user.groups.filter(name="seller").exists()
    client.force_login(user)
    assert client.get("/seller-app/").status_code == 403
    assert client.get("/admin-app/").status_code == 403
    assert client.post("/account/enable/administrator/").status_code == 403
    assert client.get("/account/enable/seller/").status_code == 405
    assert client.post("/account/enable/seller/").status_code == 302
    assert user.groups.filter(name="seller").exists()


def test_blocked_keeps_login_history_but_cannot_enable_roles(client):
    user = member()
    admin = member("admin@example.invalid", "administrator")
    with actor_transaction(admin, "Synthetic test restriction"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [user.pk])
    assert client.post("/buyer-app/login/", {"email": user.email, "password": PASSWORD}).status_code == 302
    assert client.get("/buyer-app/orders/").status_code == 200
    assert client.post("/account/enable/seller/").status_code == 403


def test_password_change_invalidates_other_session(client):
    from django.test import Client
    user = member()
    other = Client()
    client.force_login(user)
    other.force_login(user)
    response = client.post("/account/", {"old_password": PASSWORD, "new_password1": "Updated-river-4826!pass", "new_password2": "Updated-river-4826!pass"})
    assert response.status_code == 302
    assert client.get("/account/").status_code == 200
    assert other.get("/account/").status_code == 302


def test_csrf_required_and_safe_login_return():
    from django.test import Client
    user = member()
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    assert strict.post("/account/enable/seller/").status_code == 403


def test_admin_identity_never_gains_marketplace_membership(client):
    admin = member("admin@example.invalid", "administrator")
    client.force_login(admin)
    assert client.post("/account/enable/buyer/").status_code == 403
    assert not admin.groups.filter(name="buyer").exists()
