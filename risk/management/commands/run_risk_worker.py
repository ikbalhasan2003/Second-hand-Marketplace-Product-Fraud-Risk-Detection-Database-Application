import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from risk.worker import RiskWorker


class Command(BaseCommand):
    help = "Process durable PostgreSQL scan jobs with leases and frozen feature snapshots"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Attempt one job, then exit")
        parser.add_argument("--max-jobs", type=int, default=0, help="Stop after this many attempted jobs; zero runs continuously")
        parser.add_argument("--poll-seconds", type=float, default=2)
        parser.add_argument("--lease-seconds", type=int, default=120)

    def handle(self, *args, **options):
        dsn = os.getenv("WORKER_DATABASE_URL")
        if not dsn:
            raise CommandError("Set WORKER_DATABASE_URL to a dedicated worker login")
        if options["poll_seconds"] < 0.1 or options["max_jobs"] < 0:
            raise CommandError("Polling must be at least 0.1 seconds and max-jobs nonnegative")
        worker = RiskWorker(dsn, settings.ARTIFACT_ROOT, options["lease_seconds"])
        attempts = 0
        try:
            while True:
                result = worker.process_one()
                if result:
                    attempts += 1
                    self.stdout.write(f"job_id={result['job_id']} status={result['status']}")
                if options["once"] or (options["max_jobs"] and attempts >= options["max_jobs"]):
                    break
                if result is None:
                    time.sleep(options["poll_seconds"])
        except KeyboardInterrupt:
            self.stdout.write("Worker stopped; any uncompleted lease is recoverable")
