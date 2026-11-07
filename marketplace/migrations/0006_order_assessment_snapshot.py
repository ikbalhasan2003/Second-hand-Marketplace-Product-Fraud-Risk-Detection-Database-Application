from pathlib import Path
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0005_scan_publication")]
    operations = [migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunSQL(
            (Path(__file__).resolve().parent / "sql" / "008_order_assessment_snapshot.sql").read_text(encoding="utf-8")
        )],
        state_operations=[migrations.AddField(
            model_name="order", name="assessment_snapshot", field=models.JSONField(null=True)
        )],
    )]
