from pathlib import Path
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0004_admin_exports"), ("accounts", "0003_onboarding_guards")]
    operations = [migrations.RunSQL(
        (Path(__file__).resolve().parent / "sql" / "007_scan_publication.sql").read_text(encoding="utf-8")
    )]
