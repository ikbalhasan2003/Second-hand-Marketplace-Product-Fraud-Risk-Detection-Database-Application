from pathlib import Path
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0003_listing_drafts")]
    operations = [migrations.RunSQL((Path(__file__).resolve().parent / "sql" / "006_admin_exports.sql").read_text(encoding="utf-8"))]

