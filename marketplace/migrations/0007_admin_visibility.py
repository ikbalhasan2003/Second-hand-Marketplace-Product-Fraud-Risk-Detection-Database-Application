from pathlib import Path
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0006_order_assessment_snapshot")]
    operations = [migrations.RunSQL(
        (Path(__file__).resolve().parent / "sql" / "009_admin_visibility.sql").read_text(encoding="utf-8")
    )]
