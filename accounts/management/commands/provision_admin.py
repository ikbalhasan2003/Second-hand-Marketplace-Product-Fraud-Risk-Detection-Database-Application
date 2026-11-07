import getpass
import re
from pathlib import Path
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection
from django.db.models import Q
from accounts.models import User, AdministratorTransition


class Command(BaseCommand):
    help = "Explicit, idempotent sole-administrator provisioning under trusted owner credentials."

    def add_arguments(self, parser):
        parser.add_argument("email", nargs="?")
        parser.add_argument("--name", default="Marketplace administrator")
        parser.add_argument("--credentials-file")
        parser.add_argument("--replace-admin-ids", help="Exact comma-separated IDs reviewed for removal of admin privileges")
        parser.add_argument("--reason")
        parser.add_argument("--inspect", action="store_true")

    def handle(self, email=None, name=None, **options):
        if options["inspect"]:
            for user in User.objects.filter(Q(groups__name="administrator") | Q(is_staff=True) | Q(is_superuser=True)).distinct():
                self.stdout.write(f"{user.pk}: {user.email}; active={user.is_active}; status={user.status}")
            return
        password = None
        if options["credentials_file"]:
            text = Path(options["credentials_file"]).read_text(encoding="utf-8-sig")
            match = re.search(r"email:\s*([^\s,]+)\s+and password:\s*(\S+)", text, re.I)
            if not match:
                raise CommandError("Expected one administrator email/password specification in the local file.")
            email, password = match.groups()
        if not email:
            raise CommandError("Supply an email or a local credentials file.")
        email = email.strip().casefold()
        with transaction.atomic():
            # Serialize owner provisioning, including the initially empty membership set.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(724103861)")
            admins = list(User.objects.select_for_update().filter(pk__in=User.objects.filter(Q(groups__name="administrator") | Q(is_staff=True) | Q(is_superuser=True)).values("pk")))
            target = User.objects.filter(email__iexact=email).first()
            others = [u for u in admins if not target or u.pk != target.pk]
            if others:
                try:
                    reviewed = {int(v) for v in (options["replace_admin_ids"] or "").split(",") if v}
                except ValueError:
                    raise CommandError("Administrator IDs must be integers.") from None
                if reviewed != {u.pk for u in others} or not options["reason"]:
                    raise CommandError("Existing administrators preserved. Inspect, review exact replacement IDs, and supply --replace-admin-ids and --reason.")
            if target and not target.groups.filter(name="administrator").exists():
                raise CommandError("Existing identity is not an administrator; no automatic promotion or identity duplication permitted.")
            if target and (not target.is_active or target.status != "active" or not target.has_usable_password()):
                raise CommandError("Existing administrator requires explicit recovery; credentials were not reset.")
            if not target:
                if password is None:
                    password = getpass.getpass("Administrator password: ")
                    if password != getpass.getpass("Repeat password: "):
                        raise CommandError("Passwords differ.")
                target = User(email=email, full_name=name, is_staff=True)
                try:
                    target.full_clean(exclude=["password"])
                    validate_password(password, target)
                except ValidationError:
                    raise CommandError("Administrator credentials failed identity/password validation.") from None
                target.set_password(password)
                target.save()
                target.groups.add(Group.objects.get(name="administrator"))
            if others or not admins:
                AdministratorTransition.objects.create(target=target, previous_admin_ids=[u.pk for u in others],
                                                       reason=options["reason"] or "Initial controlled administrator provisioning")
            for previous in others:
                previous.groups.remove(Group.objects.get(name="administrator"))
                previous.is_staff = previous.is_superuser = False
                previous.save(update_fields=["is_staff", "is_superuser"])
            self.stdout.write(self.style.SUCCESS("Sole administrator verified. Existing passwords were not reset; user records retained."))
