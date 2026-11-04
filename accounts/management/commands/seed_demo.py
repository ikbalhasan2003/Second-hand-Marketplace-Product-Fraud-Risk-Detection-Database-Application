"""Provision explicitly synthetic local examples through normal domain transactions."""

import json
import os
import secrets
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from marketplace.db import actor_transaction, one, rows
from marketplace.services.listings import publish_listing
from marketplace.services.moderation import activate_configuration
from marketplace.services.orders import place_order


class Command(BaseCommand):
    help = "Create synthetic local Buyer/Seller/Admin accounts and real marketplace examples; never reset existing records"

    def add_arguments(self, parser):
        parser.add_argument("--reset-passwords", action="store_true", help="Explicitly rotate passwords of these three demo identities only")
        parser.add_argument("--activate-model", action="store_true", help="Verify and activate the already registered rf-synthetic-v1 model/default rules")

    def handle(self, **options):
        if not settings.DEBUG:
            raise CommandError("Synthetic demonstration provisioning requires DJANGO_DEBUG=true")
        runtime = Path(settings.BASE_DIR) / "runtime"
        runtime.mkdir(exist_ok=True)
        credential_path = runtime / "DEMO_CREDENTIALS.txt"
        json_credentials = runtime / "demo_credentials.json"
        credential_data = json.loads(json_credentials.read_text(encoding="utf-8")) if json_credentials.exists() else {"users": {}}
        password = os.getenv("DEMO_PASSWORD") or secrets.token_urlsafe(24) + "!"
        accounts = {}
        created = []
        with transaction.atomic():
            for role in ("buyer", "seller", "administrator"):
                short_role = "admin" if role == "administrator" else role
                email = f"demo.{short_role}@example.invalid"
                name = f"Synthetic Demo {short_role.title()}"
                user = User.objects.filter(email__iexact=email).first()
                if user:
                    memberships = set(user.groups.values_list("name", flat=True))
                    if user.full_name != name or memberships != {role}:
                        raise CommandError(f"Existing {email} is not the expected isolated demo identity")
                    if user.status != "active" or not user.is_active:
                        raise CommandError(f"Existing {email} is restricted; preserve its moderation state")
                else:
                    user = User(email=email, full_name=name, location="Shanghai", is_staff=role == "administrator")
                    created.append(email)
                if not user.pk or options["reset_passwords"]:
                    validate_password(password, user)
                    user.set_password(password)
                    user.save()
                    user.groups.add(Group.objects.get(name=role))
                accounts[role] = user
        if created or options["reset_passwords"]:
            # Never print credentials or write them to Git-tracked setup/evidence files.
            if credential_path.exists() and created and not options["reset_passwords"]:
                mode = "a"
            else:
                mode = "w"
            with credential_path.open(mode, encoding="utf-8") as output:
                output.write("LOCAL SYNTHETIC DEMO ONLY. Keep this private and delete after use.\n")
                for user in accounts.values():
                    if user.email in created or options["reset_passwords"]:
                        output.write(f"{user.email}\t{password}\n")
                        role = next(name for name, member in accounts.items() if member.pk == user.pk)
                        short_role = "admin" if role == "administrator" else role
                        credential_data["users"][short_role] = {"email": user.email, "password": password}
        elif not credential_path.exists() and not os.getenv("DEMO_PASSWORD"):
            self.stdout.write("Demo identities already exist; use --reset-passwords to create a new private credential record")
        seller, buyer, administrator = accounts["seller"], accounts["buyer"], accounts["administrator"]
        categories = rows("SELECT category_id,name FROM categories WHERE is_active ORDER BY category_id")
        if not categories:
            raise CommandError("Run migrations first to provision categories")
        products = []
        for index, (title, description, price, condition) in enumerate((
            ("Synthetic demo: inspected desk lamp", "Synthetic course fixture. Working used lamp; inspect before local collection. No real item is being offered.", "35.00", "good"),
            ("Synthetic demo: adjustable office chair", "Synthetic course fixture. Used adjustable chair with visible cosmetic wear. No real item is being offered.", "45.00", "fair"),
            ("Synthetic demo: camera requiring review", "Synthetic course fixture for moderation: deposit first, no inspection. These phrases are a simulated example, not proof of fraud.", "10.00", "good"),
        )):
            existing = one("""SELECT p.product_id,p.current_revision_no FROM products p JOIN product_revisions r
                              ON (r.product_id,r.revision_no)=(p.product_id,p.current_revision_no)
                              WHERE p.seller_id=%s AND r.title=%s ORDER BY p.product_id LIMIT 1""", [seller.pk, title])
            if existing:
                products.append((existing["product_id"], existing["current_revision_no"]))
            else:
                products.append(publish_listing(seller, {"title": title, "description": description, "price": Decimal(price), "original_price": None,
                                                       "condition": condition, "location": "Shanghai", "category_id": categories[index % len(categories)]["category_id"]}))
        existing_order = one("SELECT transaction_id FROM transactions WHERE product_id=%s AND buyer_id=%s ORDER BY transaction_id LIMIT 1", [products[1][0], buyer.pk])
        order_id = existing_order["transaction_id"] if existing_order else place_order(buyer, *products[1], uuid5(NAMESPACE_URL, f"synthetic-demo-order:{buyer.pk}:{products[1][0]}"), acknowledge=True)
        with actor_transaction(buyer, "Create explicit synthetic demonstration conversation and concern"):
            conversation = one("INSERT INTO conversations(product_id,buyer_id) VALUES(%s,%s) ON CONFLICT(product_id,buyer_id) DO NOTHING RETURNING conversation_id", [products[0][0], buyer.pk])
            conversation = conversation or one("SELECT conversation_id FROM conversations WHERE product_id=%s AND buyer_id=%s", [products[0][0], buyer.pk])
            if not one("SELECT 1 FROM chat_messages WHERE conversation_id=%s", [conversation["conversation_id"]]):
                rows("INSERT INTO chat_messages(conversation_id,sender_id,message_text) VALUES(%s,%s,%s)", [conversation["conversation_id"], buyer.pk, "Synthetic demo: Can I inspect this lamp before collection?"])
            report = one("SELECT report_id FROM fraud_reports WHERE product_id=%s AND reporter_id=%s ORDER BY report_id LIMIT 1", [products[2][0], buyer.pk])
            if not report:
                report = one("INSERT INTO fraud_reports(product_id,revision_no,reporter_id,reason_code,comment) VALUES(%s,%s,%s,'suspicious_price',%s) RETURNING report_id", [*products[2], buyer.pk, "Synthetic demonstration concern about price and inspection restrictions. This is pending evidence-based review, not a confirmed fraud finding."])
        with actor_transaction(seller, "Reply to explicit synthetic demonstration conversation"):
            if not one("SELECT 1 FROM chat_messages WHERE conversation_id=%s AND sender_id=%s", [conversation["conversation_id"], seller.pk]):
                rows("INSERT INTO chat_messages(conversation_id,sender_id,message_text) VALUES(%s,%s,%s)", [conversation["conversation_id"], seller.pk, "Synthetic demo: Yes, inspect the item before agreeing to an offline exchange."])
        if options["activate_model"]:
            model = one("SELECT model_id FROM risk_models WHERE version='rf-synthetic-v1'")
            rules = one("SELECT ruleset_id FROM risk_rulesets WHERE version='rf-synthetic-v1-rules'")
            if not model or not rules:
                raise CommandError("Register the real rf-synthetic-v1 artifact before requesting activation")
            active_model = one("SELECT model_id FROM risk_models WHERE state='active'")
            active_rules = one("SELECT ruleset_id FROM risk_rulesets WHERE state='active'")
            if not active_model or not active_rules or active_model["model_id"] != model["model_id"] or active_rules["ruleset_id"] != rules["ruleset_id"]:
                activate_configuration(administrator, model["model_id"], rules["ruleset_id"], "Activate verified synthetic-only local demonstration model", active_model["model_id"] if active_model else None, active_rules["ruleset_id"] if active_rules else None)
        summary = {"synthetic_only": True, "products": [product[0] for product in products], "order_id": order_id,
                   "conversation_id": conversation["conversation_id"], "report_id": report["report_id"],
                   "accounts": {role: user.email for role, user in accounts.items()}}
        (runtime / "DEMO_STATE.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        credential_data.update({key: value for key, value in summary.items() if key != "accounts"})
        json_credentials.write_text(json.dumps(credential_data, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS("Synthetic demo is ready. Private credentials: runtime/DEMO_CREDENTIALS.txt"))
        self.stdout.write(f"Products={summary['products']} order={order_id} conversation={summary['conversation_id']} report={summary['report_id']}")
