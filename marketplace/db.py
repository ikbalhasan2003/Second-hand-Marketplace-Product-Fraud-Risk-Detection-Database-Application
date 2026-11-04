"""Small parameterized SQL boundary; never interpolate request values into SQL."""
from contextlib import contextmanager
from django.db import connection, transaction


def rows(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        if cursor.description is None:
            return []
        names = [col[0] for col in cursor.description]
        return [dict(zip(names, values)) for values in cursor.fetchall()]


def one(sql, params=()):
    result = rows(sql, params)
    return result[0] if result else None


@contextmanager
def actor_transaction(user, reason="Marketplace action"):
    with transaction.atomic():
        rows("SELECT set_config('app.actor_id',%s,true),set_config('app.action_reason',%s,true)",
             [str(user.pk), reason])
        yield
