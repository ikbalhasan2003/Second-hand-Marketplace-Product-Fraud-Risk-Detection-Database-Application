import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from marketplace.db import one

pytestmark = pytest.mark.django_db


def test_demo_provisioning_is_private_separate_and_idempotent(settings, tmp_path):
    settings.DEBUG = True
    settings.BASE_DIR = tmp_path
    call_command("seed_demo", verbosity=0)
    credentials = json.loads((tmp_path / "runtime" / "demo_credentials.json").read_text())
    assert set(credentials["users"]) == {"buyer", "seller", "admin"}
    for role, details in credentials["users"].items():
        user = User.objects.get(email=details["email"])
        assert user.check_password(details["password"])
        assert list(user.groups.values_list("name", flat=True)) == ["administrator" if role == "admin" else role]
    assert one("SELECT count(*) AS n FROM products")["n"] == 3
    assert one("SELECT count(*) AS n FROM transactions")["n"] == 1
    assert one("SELECT count(*) AS n FROM chat_messages")["n"] == 2
    assert one("SELECT count(*) AS n FROM fraud_reports")["n"] == 1
    assert one("SELECT count(*) AS n FROM risk_logs")["n"] == 0
    call_command("seed_demo", verbosity=0)
    assert one("SELECT count(*) AS n FROM products")["n"] == 3
    assert one("SELECT count(*) AS n FROM transactions")["n"] == 1
    assert json.loads((tmp_path / "runtime" / "demo_credentials.json").read_text())["users"] == credentials["users"]


def test_demo_provisioning_refuses_non_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DJANGO_DEBUG"):
        call_command("seed_demo")
