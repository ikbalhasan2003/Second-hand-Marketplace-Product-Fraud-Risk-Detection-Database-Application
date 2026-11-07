from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_administratortransition"), ("marketplace", "0001_initial")]
    operations = [migrations.RunSQL("""
        CREATE TRIGGER administrator_transition_immutable
        BEFORE UPDATE OR DELETE ON administrator_transitions
        FOR EACH ROW EXECUTE FUNCTION reject_history_change();
    """, "DROP TRIGGER administrator_transition_immutable ON administrator_transitions;")]
