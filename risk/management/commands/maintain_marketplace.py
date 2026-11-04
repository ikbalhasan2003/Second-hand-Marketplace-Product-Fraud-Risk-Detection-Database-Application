import os
from datetime import date
from zoneinfo import ZoneInfo

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Run idempotent daily refresh, recover pending campaign batches, and expire unanswered orders"

    def add_arguments(self, parser):
        parser.add_argument("--daily", action="store_true", help="Create the configured-local-date refresh obligation")
        parser.add_argument("--date", type=date.fromisoformat, help="Explicit daily refresh date (YYYY-MM-DD)")
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--max-batches", type=int, default=100, help="Bound work per scheduler invocation")
        parser.add_argument("--expire", action="store_true", help="Expire one bounded batch of unanswered placed orders")

    def handle(self, *args, **options):
        dsn = os.getenv("MAINTENANCE_DATABASE_URL")
        if not dsn:
            raise CommandError("Set MAINTENANCE_DATABASE_URL to a dedicated maintenance login")
        if not 1 <= options["batch_size"] <= 1000 or options["max_batches"] < 1:
            raise CommandError("Use batch-size 1..1000 and max-batches >=1")
        with psycopg.connect(dsn, autocommit=True) as connection:
            if options["daily"]:
                local_date = options["date"] or timezone.now().astimezone(ZoneInfo(settings.TIME_ZONE)).date()
                campaign = connection.execute("SELECT create_daily_rescan(%s,%s)", (local_date, settings.TIME_ZONE)).fetchone()[0]
                self.stdout.write(f"daily_campaign_id={campaign} date={local_date}")
            batches, queued = 0, 0
            while batches < options["max_batches"]:
                found = connection.execute("SELECT campaign_id FROM risk_rescan_campaigns WHERE status IN ('queued','processing','failed') ORDER BY campaign_id LIMIT 1").fetchone()
                if not found:
                    break
                with connection.transaction():
                    queued += connection.execute("SELECT run_rescan_batch(%s,%s)", (found[0], options["batch_size"])).fetchone()[0]
                batches += 1
            expired = 0
            if options["expire"]:
                with connection.transaction():
                    expired = connection.execute("SELECT expire_unanswered_orders(%s)", (options["batch_size"],)).fetchone()[0]
            self.stdout.write(f"campaign_batches={batches} queued={queued} expired_orders={expired}")
