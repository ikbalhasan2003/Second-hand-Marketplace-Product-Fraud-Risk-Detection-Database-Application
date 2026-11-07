from pathlib import Path
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0008_policy_audit_privileges")]
    operations = [migrations.RunSQL(
        (Path(__file__).resolve().parent / "sql" / "010_account_appeals.sql").read_text(encoding="utf-8")
    )]
