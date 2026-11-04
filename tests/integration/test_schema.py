"""Focused checks of the Django/reference PostgreSQL integration boundary."""
import pytest
from django.db import connection

from marketplace.models import ProductRevision


pytestmark = pytest.mark.django_db


def test_reference_integrity_objects_survive_migrations():
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT condeferrable, condeferred FROM pg_constraint
            WHERE conname='products_current_revision_fk'
        """)
        assert cursor.fetchone() == (True, True)
        cursor.execute("""
            SELECT count(*) FROM pg_trigger
            WHERE tgname IN ('revision_immutable','image_immutable','membership_guard')
              AND NOT tgisinternal
        """)
        assert cursor.fetchone()[0] == 3
        cursor.execute("SELECT to_regclass('current_listing_risk'), to_regclass('admin_review_queue')")
        assert all(cursor.fetchone())
        cursor.execute("SELECT to_regprocedure('claim_risk_job(interval)'), to_regprocedure('place_order(bigint,bigint,integer,uuid,text)')")
        assert all(cursor.fetchone())


def test_revision_orm_uses_the_original_composite_identity():
    assert ProductRevision._meta.pk.field_names == ('product_id', 'revision_no')
    assert not ProductRevision._meta.managed
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conrelid='transactions'::regclass AND contype='f'
        """)
        assert any('FOREIGN KEY (product_id, revision_no)' in row[0] for row in cursor.fetchall())


def test_role_enabling_function_exists_without_optional_privilege_setup():
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regprocedure('enable_marketplace_role(text)')")
        assert cursor.fetchone()[0] is not None


def test_column_scoped_registration_keeps_database_identity_defaults():
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO users(email,password,full_name,location,private_contact)
            VALUES ('defaults-schema-test@example.invalid','!','Schema defaults',NULL,NULL)
            RETURNING status,is_active,is_staff,is_superuser,created_at
        """)
        status, active, staff, superuser, created = cursor.fetchone()
        assert (status, active, staff, superuser) == ('active', True, False, False)
        assert created is not None

