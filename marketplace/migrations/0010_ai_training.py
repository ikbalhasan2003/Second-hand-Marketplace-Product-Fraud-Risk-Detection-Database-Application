from pathlib import Path
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0009_account_appeals")]
    operations = [migrations.RunSQL(
        (Path(__file__).resolve().parent / "sql" / "011_ai_training.sql").read_text(encoding="utf-8")
    )]
