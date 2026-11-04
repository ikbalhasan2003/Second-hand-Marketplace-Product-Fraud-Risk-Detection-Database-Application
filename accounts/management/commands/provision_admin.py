import getpass
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import User


class Command(BaseCommand):
    help = "Provision a separate administrator under trusted management credentials. Password is prompted."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--name", required=True)

    def handle(self, email, name, **options):
        if User.objects.filter(email__iexact=email.strip()).exists():
            raise CommandError("Identity already exists; marketplace identities cannot be promoted here.")
        password = getpass.getpass("Administrator password: ")
        if password != getpass.getpass("Repeat password: "):
            raise CommandError("Passwords differ.")
        user = User(email=email.strip().casefold(), full_name=name, is_staff=True)
        validate_password(password, user)
        user.set_password(password)
        with transaction.atomic():
            user.save()
            user.groups.add(Group.objects.get(name="administrator"))
        self.stdout.write(self.style.SUCCESS("Administrator provisioned. No marketplace membership granted."))
