from pathlib import Path

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0010_ai_training"),
        ("accounts", "0003_onboarding_guards"),
        ("risk", "0001_initial"),
    ]
    operations = [migrations.RunSQL(
        (Path(__file__).parent / "sql" / "012_deployment_integrity.sql").read_text(encoding="utf-8")
    )]
