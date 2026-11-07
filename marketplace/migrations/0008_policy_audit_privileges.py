from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0007_admin_visibility")]
    operations = [migrations.RunSQL("""
        ALTER FUNCTION audit_marketplace_policy() SECURITY DEFINER;
        ALTER FUNCTION audit_marketplace_policy() SET search_path=public,pg_temp;
        REVOKE ALL ON FUNCTION audit_marketplace_policy() FROM PUBLIC;
    """)]
