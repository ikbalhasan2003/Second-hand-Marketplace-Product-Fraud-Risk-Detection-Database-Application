from django.db import migrations, models
from django.db.models.functions import Now


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0002_runtime_infrastructure")]
    operations = [migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunSQL("""
            CREATE TABLE app_listing_drafts (
                product_id bigint PRIMARY KEY REFERENCES products(product_id),
                seller_id bigint NOT NULL REFERENCES users(user_id),
                payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload)='object'),
                version integer NOT NULL DEFAULT 1 CHECK (version>0),
                updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
            );
            CREATE INDEX app_listing_drafts_seller_idx ON app_listing_drafts(seller_id,updated_at);
        """, reverse_sql=migrations.RunSQL.noop)],
        state_operations=[migrations.CreateModel(name="ListingDraft", fields=[
            ("product_id", models.BigIntegerField(primary_key=True, serialize=False)),
            ("seller_id", models.BigIntegerField()),
            ("payload", models.JSONField(default=dict)),
            ("version", models.IntegerField(default=1)),
            ("updated_at", models.DateTimeField(db_default=Now())),
        ], options={"managed": False, "db_table": "app_listing_drafts"})],
    )]
