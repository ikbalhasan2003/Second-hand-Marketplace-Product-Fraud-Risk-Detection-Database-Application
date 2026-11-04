from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0001_initial")]
    operations = [migrations.RunSQL("""
        CREATE TABLE app_rate_limits (
            bucket_key char(64) PRIMARY KEY,
            window_no bigint NOT NULL,
            hits integer NOT NULL CHECK(hits>0)
        );
        INSERT INTO auth_group(name) VALUES('buyer'),('seller'),('administrator') ON CONFLICT DO NOTHING;
        INSERT INTO categories(name,description) VALUES
            ('Electronics','Devices and accessories'),('Furniture','Home furniture'),
            ('Books','Books and course materials'),('Clothing','Clothing and accessories'),
            ('Sports','Sports and outdoor equipment') ON CONFLICT DO NOTHING;
        """, reverse_sql=migrations.RunSQL.noop)]
