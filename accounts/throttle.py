"""Shared PostgreSQL fixed-window counters, serialized through one UPSERT."""
import hashlib
import time
from django.conf import settings
from django.core.exceptions import PermissionDenied
from marketplace.db import one


class RateLimited(PermissionDenied):
    pass


def throttle(kind, identity):
    count, period = settings.RATE_LIMITS[kind]
    key = hashlib.sha256(f"{kind}:{identity}".encode()).hexdigest()
    window = int(time.time()) // period
    result = one("""INSERT INTO app_rate_limits(bucket_key,window_no,hits) VALUES(%s,%s,1)
        ON CONFLICT(bucket_key) DO UPDATE SET
        hits=CASE WHEN app_rate_limits.window_no=excluded.window_no THEN app_rate_limits.hits+1 ELSE 1 END,
        window_no=excluded.window_no RETURNING hits""", [key, window])
    if result["hits"] > count:
        raise RateLimited("Too many requests. Please wait before trying again.")
