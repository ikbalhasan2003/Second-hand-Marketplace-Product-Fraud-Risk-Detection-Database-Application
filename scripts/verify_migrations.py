"""Disposable fresh/legacy-upgrade checks and verified backup before working migration.

Run with the controlled owner connection from .env. Credentials never enter argv/logs.
Databases and private backup evidence are retained under runtime/migration-checks.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.conf import settings  # noqa: E402
import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--apply-working", action="store_true")
    args = parser.parse_args()
    config = settings.DATABASES["default"]
    connect = dict(host=config["HOST"], port=config["PORT"], user=config["USER"],
                   password=config["PASSWORD"], dbname=config["NAME"], connect_timeout=5)
    env = os.environ.copy()
    env.update({"PGHOST": str(connect["host"]), "PGPORT": str(connect["port"]),
                "PGUSER": connect["user"], "PGPASSWORD": connect["password"]})
    run_id = uuid4().hex[:12]
    evidence = BASE / "runtime" / "migration-checks" / run_id
    evidence.mkdir(parents=True)
    report = {"run_id": run_id, "status": "incomplete", "databases": {}, "working_migrations_ran": []}

    def command(argv, database):
        child_env = dict(env, PGDATABASE=database)
        result = subprocess.run([str(a) for a in argv], cwd=BASE, env=child_env,
                                capture_output=True, text=True)
        # Database exceptions may include connection details; keep failure output private.
        with (evidence / "commands.log").open("a", encoding="utf-8") as log:
            log.write(f"database={database} command={Path(str(argv[0])).name} {' '.join(map(str, argv[1:]))}\n")
            log.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("Database verification command failed; inspect private commands.log")

    def migrate(database, *target):
        command([sys.executable, "manage.py", "migrate", *target, "--noinput"], database)

    def db(database):
        return psycopg.connect(**dict(connect, dbname=database), autocommit=True)

    def create(connection, label):
        name = f"step10_{label}_{run_id}"
        connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        report["databases"][label] = name
        return name

    def grants(database):
        with db(database) as conn:
            for name in ("008_privileges.sql", "009_app_privileges.sql"):
                conn.execute((BASE / "database" / name).read_text(encoding="utf-8"))
            for role, table, permission, expected in [
                ("secondhand_web", "account_appeals", "INSERT", True),
                ("secondhand_web", "ai_training_jobs", "UPDATE", False),
                ("secondhand_worker", "ai_training_jobs", "UPDATE", False),
                ("secondhand_maintenance", "account_appeals", "SELECT", False),
                ("secondhand_training", "risk_models", "INSERT", True),
                ("secondhand_training", "risk_models", "UPDATE", False),
                ("secondhand_training", "chat_messages", "SELECT", False),
                ("secondhand_web", "administrator_transitions", "INSERT", False),
            ]:
                assert conn.execute("SELECT has_table_privilege(%s,%s,%s)",
                                    (role, table, permission)).fetchone()[0] == expected
            assert not conn.execute("SELECT has_column_privilege('secondhand_training','users','private_contact','SELECT')").fetchone()[0]
            assert conn.execute("SELECT has_column_privilege('secondhand_training','ai_training_jobs','status','UPDATE')").fetchone()[0]
            assert not conn.execute("SELECT has_column_privilege('secondhand_training','ai_training_jobs','configuration','UPDATE')").fetchone()[0]
            for role in ("secondhand_training", "secondhand_worker", "secondhand_web", "secondhand_maintenance"):
                assert not conn.execute("SELECT has_function_privilege(%s,'guard_training_job_history()','EXECUTE')", (role,)).fetchone()[0]

    def history(conn):
        return {table: conn.execute(sql.SQL("SELECT jsonb_agg(to_jsonb(t) ORDER BY {}) FROM {} t").format(
            sql.SQL(key), sql.Identifier(table))).fetchone()[0]
            for table, key in [("product_revisions", "product_id,revision_no"),
                               ("order_status_history", "event_id"), ("moderation_reviews", "review_id"),
                               ("admin_audit_logs", "audit_id")]}

    def appeal_race(database):
        with db(database) as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.actor_id','1',true),set_config('app.action_reason','Disposable appeal race',true)")
                conn.execute("UPDATE users SET status='blocked' WHERE user_id=4")
        barrier = Barrier(2)

        def submit(_):
            with db(database) as conn:
                barrier.wait(timeout=10)
                try:
                    with conn.transaction():
                        conn.execute("SET LOCAL lock_timeout='10s'")
                        conn.execute("SET LOCAL ROLE secondhand_web")
                        conn.execute("SELECT set_config('app.actor_id','4',true)")
                        conn.execute("INSERT INTO account_appeals(user_id,reason) VALUES(4,'Synthetic concurrent appeal')")
                    return "inserted"
                except psycopg.errors.UniqueViolation:
                    return "duplicate_rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(submit, range(2))) == ["duplicate_rejected", "inserted"]
        report["appeal_two_connection_race"] = "passed"

    def catalog(database):
        queries = {
            "columns": "SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY 1,2",
            "constraints": "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1,2",
            "indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1,2",
            "triggers": "SELECT tgrelid::regclass::text,tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace) ORDER BY 1,2",
            "functions": "SELECT proname,pg_get_function_identity_arguments(oid),pg_get_functiondef(oid) FROM pg_proc WHERE pronamespace='public'::regnamespace ORDER BY 1,2",
        }
        with db(database) as conn:
            return {name: conn.execute(query).fetchall() for name, query in queries.items()}

    try:
        with db(connect["dbname"]) as working:
            report["target"] = working.execute("SELECT current_database(),current_user,inet_server_addr()::text,inet_server_port()").fetchone()
            before = working.execute("SELECT app,name FROM django_migrations ORDER BY app,name").fetchall()
            fresh = create(working, "fresh")
            migrate(fresh)
            grants(fresh)
            upgrade = create(working, "upgrade")
            migrate(upgrade, "marketplace", "0004")
            # Adapt the existing synthetic SQL fixture only in this disposable database.
            seed = (BASE / "database" / "006_seed.sql").read_text(encoding="utf-8")
            seed = re.sub(r"INSERT INTO auth_group\(id,name\).*?;", "", seed, flags=re.S)
            seed = re.sub(r"INSERT INTO categories\(category_id,name,description\).*?;", "", seed, flags=re.S)
            with db(upgrade) as conn:
                conn.execute(seed)
                legacy_history = history(conn)
            migrate(upgrade, "marketplace", "0010")
            migrate(upgrade)
            with db(upgrade) as conn:
                assert history(conn) == legacy_history
                assert conn.execute("SELECT assessment_snapshot IS NULL FROM transactions WHERE transaction_id=100").fetchone()[0]
                assert conn.execute("SELECT condeferrable AND condeferred FROM pg_constraint WHERE conname='products_current_revision_fk'").fetchone()[0]
                assert conn.execute("SELECT count(*) FROM account_appeals").fetchone()[0] == 0
                assert conn.execute("SELECT count(*) FROM ai_training_jobs").fetchone()[0] == 0
            grants(upgrade)
            assert catalog(fresh) == catalog(upgrade), "Fresh/upgrade schema catalogs differ"
            report["fresh_upgrade_catalogs"] = "identical"
            appeal_race(upgrade)
            command([sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"], fresh)
            command([sys.executable, "manage.py", "check"], fresh)
            report["fresh_upgrade_privileges"] = "passed"
            if args.apply_working:
                backup = evidence / "working-before.dump"
                command([args.pg_bin / "pg_dump.exe", "--format=custom", "--file", backup], connect["dbname"])
                report["backup_sha256"] = hashlib.sha256(backup.read_bytes()).hexdigest()
                restore = create(working, "restore")
                command([args.pg_bin / "pg_restore.exe", "--exit-on-error", "--dbname", restore, backup], restore)
                with db(restore) as restored:
                    assert restored.execute("SELECT app,name FROM django_migrations ORDER BY app,name").fetchall() == before
                    for table in ("users", "products", "transactions", "admin_audit_logs", "ai_training_jobs"):
                        query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                        assert restored.execute(query).fetchone() == working.execute(query).fetchone()
                report["backup_restore"] = "passed"
                migrate(connect["dbname"])
                grants(connect["dbname"])
                after = working.execute("SELECT app,name FROM django_migrations ORDER BY app,name").fetchall()
                report["working_migrations_ran"] = [row for row in after if row not in before]
                command([sys.executable, "manage.py", "migrate", "--check"], connect["dbname"])
                report["working_grants"] = ["008_privileges.sql", "009_app_privileges.sql"]
            report["status"] = "passed"
    finally:
        (evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
