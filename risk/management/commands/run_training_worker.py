import os
import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ml.training.jobs import process_one


class Command(BaseCommand):
    help = "Train frozen datasets using trusted operator credentials; candidates require explicit activation"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=5)

    def handle(self, *args, **options):
        dsn = os.getenv("REGISTRATION_DATABASE_URL")
        if not dsn:
            raise CommandError("Set REGISTRATION_DATABASE_URL to trusted operator credentials; web and risk-worker roles cannot register model bytes.")
        if options["poll_seconds"] < 0.1:
            raise CommandError("Polling must be at least 0.1 seconds")
        try:
            while True:
                result = process_one(dsn, settings.ARTIFACT_ROOT)
                if result:
                    self.stdout.write(f"job_id={result['job_id']} status={result['status']}")
                if options["once"]:
                    break
                time.sleep(options["poll_seconds"])
        except KeyboardInterrupt:
            self.stdout.write("Trainer stopped; interrupted jobs are recovered by the next trainer.")
