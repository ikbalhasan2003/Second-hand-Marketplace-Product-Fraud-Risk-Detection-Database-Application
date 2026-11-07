import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError, IntegrityError, transaction
from accounts.models import User
from marketplace.db import actor_transaction, rows

pytestmark = pytest.mark.django_db
PASSWORD = "Stone-river-4826!pass"


def member(email="member@example.invalid", role="buyer"):
    user = User.objects.create_user(email, PASSWORD, full_name="Test Member")
    user.groups.add(Group.objects.get(name=role))
    return user


def test_registration_normalizes_identity_and_grants_only_selected_role(client):
    response = client.post("/register/", {"email": " New@Example.invalid ", "full_name": "New Member", "password": PASSWORD, "password_confirm": PASSWORD, "role": "buyer", "is_staff": "true"})
    assert response.status_code == 302
    user = User.objects.get(email="new@example.invalid")
    assert user.check_password(PASSWORD)
    assert user.password.startswith("bcrypt_sha256$")
    assert list(user.groups.values_list("name", flat=True)) == ["buyer"]
    assert not user.is_staff and not user.is_superuser
    response = client.post("/register/", {"email": "NEW@example.invalid", "full_name": "Duplicate", "password": PASSWORD, "password_confirm": PASSWORD})
    assert response.status_code == 200
    assert User.objects.filter(email__iexact="new@example.invalid").count() == 1


def test_case_insensitive_database_duplicate_rejected():
    member()
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("MEMBER@example.invalid", PASSWORD, full_name="Duplicate")


def test_login_does_not_enable_role_and_app_gates_apply(client):
    user = member()
    assert client.post("/login/", {"email": user.email, "password": PASSWORD}).status_code == 302
    assert not user.groups.filter(name="seller").exists()
    client.force_login(user)
    assert client.get("/sell/").status_code == 403
    assert client.get("/admin-app/").status_code == 403
    assert client.post("/account/enable/administrator/").status_code == 403
    assert client.get("/account/enable/seller/").status_code == 200
    assert client.post("/account/enable/seller/", {"full_name": "Test Seller", "location": "Shanghai", "private_contact": "support@example.invalid"}).status_code == 302
    assert user.groups.filter(name="seller").exists()


def test_blocked_keeps_login_history_but_cannot_enable_roles(client):
    user = member()
    admin = member("admin@example.invalid", "administrator")
    with actor_transaction(admin, "Synthetic test restriction"):
        rows("UPDATE users SET status='blocked' WHERE user_id=%s", [user.pk])
    assert client.post("/login/", {"email": user.email, "password": PASSWORD}).status_code == 302
    assert client.get("/orders/").status_code == 200
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


def test_buyer_minimal_and_seller_requires_profile(client):
    assert client.post("/register/", {"email": "minimal@example.invalid", "password": PASSWORD, "password_confirm": PASSWORD}).status_code == 302
    user = User.objects.get(email="minimal@example.invalid")
    assert user.full_name.startswith("Member ")
    assert client.post("/account/enable/seller/", {}).status_code == 200
    assert not user.groups.filter(name="seller").exists()
    assert client.post("/account/enable/seller/", {"full_name": "Shop", "location": "Shanghai", "private_contact": "bad"}).status_code == 200
    assert not user.groups.filter(name="seller").exists()
    assert client.post("/logout/").status_code == 302
    assert client.get("/account/").status_code == 302
    assert client.post("/register/", {"email": "seller-new@example.invalid", "role": "seller", "password": PASSWORD, "password_confirm": PASSWORD}).status_code == 200
    assert not User.objects.filter(email="seller-new@example.invalid").exists()
    response = client.post("/register/", {"email": "seller-new@example.invalid", "role": "seller", "password": PASSWORD, "password_confirm": PASSWORD, "full_name": "Seller", "location": "Shanghai", "private_contact": "+86 13812345678"})
    assert response.status_code == 302
    seller = User.objects.get(email="seller-new@example.invalid")
    assert seller.private_contact == "+86 13812345678"
    assert list(seller.groups.values_list("name", flat=True)) == ["seller"]


@pytest.mark.parametrize("password,confirmation", [("short", "short"), (PASSWORD, "different"), ("123456789012", "123456789012")])
def test_registration_password_validation(client, password, confirmation):
    assert client.post("/register/", {"email": "invalid@example.invalid", "password": password, "password_confirm": confirmation}).status_code == 200
    assert not User.objects.filter(email="invalid@example.invalid").exists()


def test_controlled_admin_transition_and_idempotence():
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from unittest.mock import patch
    from accounts.models import AdministratorTransition
    previous = member("old-admin@example.invalid", "administrator")
    with pytest.raises(CommandError):
        call_command("provision_admin", "sole@example.invalid")
    assert previous.groups.filter(name="administrator").exists()
    with patch("getpass.getpass", return_value=PASSWORD):
        call_command("provision_admin", "sole@example.invalid", replace_admin_ids=str(previous.pk), reason="Reviewed synthetic transition")
    sole = User.objects.get(email="sole@example.invalid")
    assert sole.check_password(PASSWORD)
    assert User.objects.filter(pk=previous.pk).exists()
    assert not previous.groups.filter(name="administrator").exists()
    assert AdministratorTransition.objects.get().previous_admin_ids == [previous.pk]
    hashed = sole.password
    call_command("provision_admin", "sole@example.invalid")
    sole.refresh_from_db()
    assert sole.password == hashed
    assert AdministratorTransition.objects.count() == 1
    buyer = member("no-promotion@example.invalid")
    with pytest.raises(CommandError):
        call_command("provision_admin", buyer.email)


def test_multiple_admin_review_requires_exact_ids_and_preserves_records():
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from unittest.mock import patch
    from accounts.models import AdministratorTransition
    first = member("first-admin@example.invalid", "administrator")
    second = member("second-admin@example.invalid", "administrator")
    with pytest.raises(CommandError):
        call_command("provision_admin", "replacement@example.invalid", replace_admin_ids=str(first.pk), reason="Incomplete review")
    assert User.objects.filter(groups__name="administrator").count() == 2
    with patch("getpass.getpass", return_value=PASSWORD):
        call_command("provision_admin", "replacement@example.invalid", replace_admin_ids=f"{first.pk},{second.pk}", reason="Reviewed both prior administrators")
    assert User.objects.filter(groups__name="administrator").count() == 1
    assert User.objects.filter(pk__in=[first.pk, second.pk]).count() == 2
    with pytest.raises(DatabaseError), transaction.atomic():
        AdministratorTransition.objects.update(reason="Alter history")


def test_demo_cannot_create_second_administrator(settings, tmp_path):
    from django.core.management import call_command
    from django.core.management.base import CommandError
    settings.DEBUG = True
    settings.BASE_DIR = tmp_path
    member("sole-existing@example.invalid", "administrator")
    with pytest.raises(CommandError, match="administrator already exists"):
        call_command("seed_demo")
    assert User.objects.filter(groups__name="administrator").count() == 1
    assert not User.objects.filter(email="demo.admin@example.invalid").exists()
