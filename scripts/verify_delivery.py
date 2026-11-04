"""Measured disposable PostgreSQL/search/worker/coordinated-restore delivery drill.

Run as a database creation/role-management operator on a local disposable server.
No existing database is reset. Every database name is unique and retained for review.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files_manifest(root):
    return {path.relative_to(root).as_posix(): sha256(path) for path in sorted(root.rglob("*")) if path.is_file()}


def percentile95(values):
    return sorted(values)[max(0, math.ceil(len(values) * 0.95) - 1)]


def setup_django(workspace, storage):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["DJANGO_DEBUG"] = "true"
    os.environ["PUBLIC_MEDIA_ROOT"] = str(workspace / storage / "public")
    os.environ["PRIVATE_MEDIA_ROOT"] = str(workspace / storage / "private")
    os.environ["ARTIFACT_ROOT"] = str(workspace / storage / "artifacts")
    import django
    django.setup()


def member(email, role):
    from accounts.models import User
    from django.contrib.auth.models import Group
    user = User.objects.create_user(email, full_name=f"Synthetic delivery {role}", location="Shanghai")
    user.groups.add(Group.objects.get(name=role))
    return user


def migrate():
    from django.core.management import call_command
    call_command("migrate", verbosity=0, interactive=False)


def seed_search(count):
    """Bulk seed through genuine publication/revision/queue triggers, with v1 fingerprints."""
    from marketplace.db import actor_transaction, one, rows
    from ml.contract import text_fingerprint
    from django.db import connection
    seller = member("search-seller@example.invalid", "seller")
    category_ids = [row["category_id"] for row in rows("SELECT category_id FROM categories ORDER BY category_id")]
    started = time.perf_counter()
    with actor_transaction(seller, "Synthetic 10000-listing delivery workload"):
        products = rows("INSERT INTO products(seller_id) SELECT %s FROM generate_series(1,%s) RETURNING product_id", [seller.pk, count])
        facts = []
        for number, product in enumerate(products):
            title = f"Desk lamp {number}" if number % 2 == 0 else f"Used study book {number}"
            description = "Used household item for study and reading with ordinary visible wear"
            facts.append([product["product_id"], category_ids[number % len(category_ids)], title, description,
                          Decimal(10 + number % 200), ("like_new", "good", "fair", "poor")[number % 4],
                          ("Shanghai", "Beijing", "Hangzhou")[number % 3], text_fingerprint(title, description)])
        with connection.cursor() as cursor:
            cursor.executemany("""INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,
                price,currency,condition,location,text_fingerprint) VALUES(%s,1,%s,%s,%s,%s,'USD',%s,%s,%s)""", facts)
        rows("UPDATE products SET current_revision_no=1,availability='available' WHERE seller_id=%s", [seller.pk])
    rows("ANALYZE products")
    rows("ANALYZE product_revisions")
    rows("ANALYZE risk_scan_jobs")
    return {"count": one("SELECT count(*) AS n FROM products")["n"], "seed_seconds": time.perf_counter() - started}


def benchmark_search():
    from django.db import connections
    from django.test import Client
    barrier = threading.Barrier(10)
    urls = ["/buyer-app/listings/?q=lamp", "/buyer-app/listings/?q=study&condition=good",
            "/buyer-app/listings/?maximum=120&location=Shanghai", "/buyer-app/listings/?q=lamp&risk=low",
            "/buyer-app/listings/?q=book&sort=price"]
    # Warm every query before timed concurrent requests; no images are requested.
    client = Client()
    for url in urls:
        assert client.get(url).status_code == 200

    def client_work(index):
        local = Client()
        durations, statuses = [], []
        barrier.wait()
        try:
            for offset in range(10):
                start = time.perf_counter()
                response = local.get(urls[(index + offset) % len(urls)])
                durations.append(time.perf_counter() - start)
                statuses.append(response.status_code)
        finally:
            connections.close_all()
        return durations, statuses

    with ThreadPoolExecutor(max_workers=10) as pool:
        batches = list(pool.map(client_work, range(10)))
    durations = [duration for batch, _ in batches for duration in batch]
    statuses = [status for _, batch in batches for status in batch]
    p95 = percentile95(durations)
    return {"concurrent_clients": 10, "requests": len(durations), "http_statuses": sorted(set(statuses)),
            "p95_seconds": p95, "maximum_seconds": max(durations), "mean_seconds": sum(durations) / len(durations),
            "target_seconds": 1, "passed": p95 <= 1 and all(status == 200 for status in statuses),
            "method": "Django in-process HTTP Client including middleware/view/templates/PostgreSQL; ten threads, ten requests each, five warmed query variants; excludes socket/TLS and image transfer"}


def warm_source(workspace):
    import psycopg
    from django.conf import settings
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import connection
    from marketplace.db import actor_transaction, one, rows
    from marketplace.services.listings import publish_listing
    from marketplace.uploads import store_image, validate_image
    from ml.training.register import register
    from PIL import Image
    from risk.worker import RiskWorker

    seller = member("restore-seller@example.invalid", "seller")
    buyer = member("restore-buyer@example.invalid", "buyer")
    outsider = member("restore-outsider@example.invalid", "buyer")
    admin = member("restore-admin@example.invalid", "administrator")
    artifact_root = Path(settings.ARTIFACT_ROOT)
    dataset = artifact_root / "datasets" / "synthetic-v1"
    model = artifact_root / "models" / "rf-synthetic-v1"
    with psycopg.connect() as operator:
        ids = register(operator, dataset, model, artifact_root, admin.pk, "Register actual fitted synthetic delivery model")
    with actor_transaction(admin, "Activate verified delivery model and rules"):
        rows("SELECT activate_risk_configuration(%s,%s)", [ids["model_id"], ids["ruleset_id"]])
    category = one("SELECT category_id FROM categories ORDER BY category_id LIMIT 1")["category_id"]
    facts = {"title": "Restorable desk lamp", "description": "Synthetic lamp with ordinary used condition.",
             "category_id": category, "price": Decimal("25.00"), "original_price": None,
             "condition": "good", "location": "Shanghai"}
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "navy").save(buffer, format="PNG")
    image_bytes = buffer.getvalue()
    warmup, _ = publish_listing(seller, facts, [SimpleUploadedFile("lamp.png", image_bytes)])
    worker = RiskWorker("", artifact_root)
    assert worker.process_one()["status"] == "succeeded"
    products = []
    for number in range(20):
        product, _ = publish_listing(seller, facts | {"title": f"Timed lamp {number}"})
        products.append(product)
    pending = one("SELECT count(*) AS n FROM risk_scan_jobs WHERE status='queued'")["n"]
    assert pending == 20
    for _ in range(20):
        outcome = worker.process_one()
        assert outcome and outcome["status"] == "succeeded", outcome
    latency = rows("""SELECT extract(epoch FROM completed_at-created_at)::float AS elapsed FROM risk_scan_jobs
        WHERE product_id=ANY(%s) ORDER BY job_id""", [products])
    times = [row["elapsed"] for row in latency]
    assert len(times) == 20
    scan = {"jobs": 20, "workers": 1, "waiting_at_start": pending, "model_preloaded": True,
            "p95_seconds": percentile95(times), "maximum_seconds": max(times), "target_seconds": 15,
            "passed": percentile95(times) <= 15,
            "method": "Twenty actual publications then one reusable RiskWorker; database completed_at minus job created_at, including queue wait; one separate real warmup prediction"}
    with actor_transaction(buyer, "Create recoverable synthetic purchase and report"):
        order = one("SELECT place_order(%s,%s,1,%s,%s) AS id", [buyer.pk, warmup, uuid4(), "c" * 64])["id"]
        report = one("""INSERT INTO fraud_reports(product_id,revision_no,reporter_id,transaction_id,reason_code,comment)
            VALUES(%s,1,%s,%s,'other','Synthetic restore evidence fixture') RETURNING report_id""", [warmup, buyer.pk, order])["report_id"]
        image = store_image(validate_image(SimpleUploadedFile("evidence.png", image_bytes)), private=True)
        attachment = one("""INSERT INTO report_attachments(report_id,storage_key,sort_order,content_type,byte_size,content_sha256)
            VALUES(%s,%s,0,%s,%s,%s) RETURNING attachment_id""", [report, image["storage_key"], image["content_type"], image["byte_size"], image["content_sha256"]])["attachment_id"]
    with actor_transaction(admin, "Record restorable synthetic decision chain"):
        review = one("""INSERT INTO moderation_reviews(product_id,revision_no,report_id,reviewer_id,verdict,reason,evidence_summary)
            VALUES(%s,1,%s,%s,'legitimate','Synthetic fixture outcome','Synthetic scenario specification') RETURNING review_id""", [warmup, report, admin.pk])["review_id"]
        rows("""INSERT INTO moderation_reviews(product_id,revision_no,report_id,reviewer_id,verdict,reason,evidence_summary,supersedes_review_id)
            VALUES(%s,1,%s,%s,'unresolved','Synthetic uncertainty correction','More evidence required',%s)""", [warmup, report, admin.pk, review])
    # Harden the snapshot before backup; restore must preserve process ACLs too.
    with connection.cursor() as cursor:
        cursor.execute((BASE / "database" / "008_privileges.sql").read_text(encoding="utf-8"))
        cursor.execute((BASE / "database" / "009_app_privileges.sql").read_text(encoding="utf-8"))
    counts = {table: one(f"SELECT count(*) AS n FROM {table}")["n"] for table in (
        "products", "product_revisions", "transactions", "fraud_reports", "report_attachments",
        "risk_logs", "risk_scan_jobs", "moderation_reviews", "admin_audit_logs", "dataset_records")}
    return {"warm_scan": scan, "fixture": {"buyer_id": buyer.pk, "seller_id": seller.pk, "outsider_id": outsider.pk,
        "admin_id": admin.pk, "product_id": warmup, "order_id": order, "report_id": report, "attachment_id": attachment},
        "counts": counts, "database": os.environ["PGDATABASE"], "model_ids": ids,
        "storage_manifests": {name: files_manifest(workspace / "source" / name) for name in ("public", "private", "artifacts")}}


def verify_restored(workspace):
    from accounts.models import User
    from django.conf import settings
    from django.test import Client
    from marketplace.db import one
    from ml.training.artifacts import load_trusted_pipeline
    original = json.loads((workspace / "source.json").read_text(encoding="utf-8"))
    ids = original["fixture"]
    checks = {}
    checks["restricted_effective_role"] = one("SELECT current_user AS name")["name"] == os.environ["PGUSER"]
    client = Client()
    client.force_login(User.objects.get(pk=ids["buyer_id"]))
    checks["purchased_snapshot_http"] = client.get(f"/buyer-app/orders/{ids['order_id']}/").status_code == 200
    checks["report_status_http"] = client.get(f"/buyer-app/reports/{ids['report_id']}/").status_code == 200
    response = client.get(f"/buyer-app/evidence/{ids['attachment_id']}/")
    checks["private_evidence_reporter_http"] = response.status_code == 200
    response.close()
    client.force_login(User.objects.get(pk=ids["outsider_id"]))
    checks["private_evidence_unrelated_denied"] = client.get(f"/buyer-app/evidence/{ids['attachment_id']}/").status_code == 404
    checks["unrelated_order_denied"] = client.get(f"/buyer-app/orders/{ids['order_id']}/").status_code == 404
    client.force_login(User.objects.get(pk=ids["seller_id"]))
    checks["seller_historical_revision_http"] = client.get(f"/seller-app/listings/{ids['product_id']}/revisions/1/").status_code == 200
    checks["seller_private_evidence_denied"] = client.get(f"/buyer-app/evidence/{ids['attachment_id']}/").status_code == 404
    client.force_login(User.objects.get(pk=ids["admin_id"]))
    response = client.get(f"/buyer-app/evidence/{ids['attachment_id']}/")
    checks["administrator_private_evidence_http"] = response.status_code == 200
    response.close()
    for url in ("/admin-app/", "/admin-app/reviews/", "/admin-app/models/", "/admin-app/audit-log/", "/admin-app/exports/"):
        checks["restored_page_" + url.strip("/").replace("/", "_")] = client.get(url).status_code == 200
    checks["web_cannot_delete_audit"] = not one("SELECT has_table_privilege(current_user,'admin_audit_logs','DELETE') AS allowed")["allowed"]
    checks["web_cannot_update_risk_results"] = not one("SELECT has_table_privilege(current_user,'risk_logs','UPDATE') AS allowed")["allowed"]
    checks["web_cannot_claim_worker_jobs"] = not one("SELECT has_function_privilege(current_user,'claim_risk_job(interval)','EXECUTE') AS allowed")["allowed"]
    for table, expected in original["counts"].items():
        checks[f"table_count_{table}"] = one(f"SELECT count(*) AS n FROM {table}")["n"] == expected
    for name, manifest in original["storage_manifests"].items():
        checks[f"checksums_{name}"] = files_manifest(workspace / "restored" / name) == manifest
    model = one("SELECT * FROM risk_models WHERE model_id=%s", [original["model_ids"]["model_id"]])
    schema = one("SELECT version FROM feature_schemas WHERE feature_schema_id=%s", [model["feature_schema_id"]])["version"]
    load_trusted_pipeline(Path(settings.ARTIFACT_ROOT), model["artifact_key"], model["artifact_sha256"], schema,
                          model["dependency_manifest"], model["class_mapping"])
    checks["trusted_pipeline_loads"] = True
    checks["result_job_revision_links"] = one("""SELECT count(*) AS n FROM risk_logs l JOIN risk_scan_jobs j USING(job_id)
        JOIN product_revisions r ON (r.product_id,r.revision_no)=(j.product_id,j.revision_no)""")["n"] == original["counts"]["risk_logs"]
    checks["latest_unresolved_chain_retained"] = one("SELECT verdict FROM latest_effective_reviews WHERE product_id=%s", [ids["product_id"]])["verdict"] == "unresolved"
    return {"passed": all(checks.values()), "checks": checks, "database": os.environ["PGDATABASE"],
            "runtime_user": os.environ["PGUSER"], "source_writes_quiesced": True,
            "method": "Custom-format pg_dump/pg_restore into a new database, coordinated closed media/artifact copy, real HTTP role/ownership checks under a separate restricted web login"}


def phase(args):
    setup_django(args.workspace, "restored" if args.phase == "restore" else "source")
    if args.phase == "search":
        migrate()
        result = {"workload": seed_search(10000), "search": benchmark_search()}
    elif args.phase == "source":
        migrate()
        result = warm_source(args.workspace)
    else:
        result = verify_restored(args.workspace)
    write_json(args.workspace / f"{args.phase}.json", result)


def reproduce_model(workspace):
    """Repeat actual generation/fitting; compare dataset, all predictions and evaluation."""
    import joblib
    import numpy as np
    from ml.datasets.generate import generate_records
    from ml.datasets.io import load_dataset
    from ml.training.preprocessing import matrix
    from ml.training.train import train
    original = BASE / "artifacts" / "models" / "rf-synthetic-v1"
    dataset = BASE / "artifacts" / "datasets" / "synthetic-v1"
    records, manifest = load_dataset(dataset)
    same_records = records == generate_records(len(records), manifest["seed"])
    repeated = workspace / "reproduced-model"
    metadata = train(dataset, repeated, "rf-reproducibility-verification")
    before = joblib.load(original / "pipeline.joblib")
    after = joblib.load(repeated / "pipeline.joblib")
    predictors = matrix(records)
    predictions_match = bool(np.array_equal(before.predict_proba(predictors), after.predict_proba(predictors)))
    report_before = json.loads((original / "evaluation.json").read_text())
    report_after = json.loads((repeated / "evaluation.json").read_text())
    evaluation_match = report_before == report_after
    return {"passed": same_records and predictions_match and evaluation_match, "records": len(records),
        "seed": manifest["seed"], "dataset_sha256": manifest["dataset_sha256"],
        "generation_records_identical": same_records, "all_probabilities_identical": predictions_match,
        "complete_evaluation_identical": evaluation_match,
        "pipeline_bytes_identical": sha256(original / "pipeline.joblib") == metadata["artifact_sha256"],
        "repeated_artifact_sha256": metadata["artifact_sha256"], "synthetic_only": True,
        "test_metrics": {name: {key: value for key, value in data["test"]["all"].items() if key != "false_positive_examples"}
                         for name, data in report_before["models"].items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, default=BASE / ".local" / "pg-server" / "pgsql" / "bin")
    parser.add_argument("--output", type=Path, default=BASE / "docs" / "evidence" / "delivery.json")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--phase", choices=("search", "source", "restore"))
    args = parser.parse_args(argv)
    if args.phase:
        phase(args)
        return
    import psycopg
    from psycopg import sql
    from importlib.metadata import version
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid4().hex[:8]
    workspace = args.workspace or BASE / "runtime" / "delivery" / run_id
    workspace.mkdir(parents=True, exist_ok=False)
    databases = {name: f"delivery_{name}_{run_id}" for name in ("search", "source", "restore")}
    web_user = "delivery_web_" + uuid4().hex[:12]
    evidence = {"run_id": run_id, "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "all_marketplace_and_training_data_synthetic": True, "databases": databases,
        "workspace": str(workspace.relative_to(BASE)), "hardware": {"platform": platform.platform(),
            "processor": platform.processor(), "logical_cpus": os.cpu_count()},
        "dependencies": {name: version(name) for name in ("Django", "psycopg", "scikit-learn", "numpy", "Pillow")},
        "python": platform.python_version(), "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BASE, text=True).strip(),
        "limitations": ["Search HTTP timing excludes socket/TLS/image transfer", "Single-host synthetic workloads; no real-world load or fraud claim",
            "Operator-run quiesced restore drill, not an online point-in-time recovery test", "Generated databases and recovery files retained for review"]}
    try:
        with psycopg.connect(dbname="postgres", autocommit=True) as operator:
            evidence["postgresql"] = operator.execute("SELECT version()").fetchone()[0]
            for name in databases.values():
                operator.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            operator.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT").format(sql.Identifier(web_user)))
        artifacts = workspace / "source" / "artifacts"
        shutil.copytree(BASE / "artifacts" / "datasets" / "synthetic-v1", artifacts / "datasets" / "synthetic-v1")
        shutil.copytree(BASE / "artifacts" / "models" / "rf-synthetic-v1", artifacts / "models" / "rf-synthetic-v1")
        for mode in ("search", "source"):
            print(f"Running isolated delivery phase: {mode}", flush=True)
            environment = {**os.environ, "PGDATABASE": databases[mode], "DJANGO_DEBUG": "true", "PGOPTIONS": "-c statement_timeout=15000"}
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--phase", mode, "--workspace", str(workspace)],
                           cwd=BASE, env=environment, check=True)
        print("Creating coordinated recovery set and restoring isolated target", flush=True)
        dump = workspace / "recovery" / "database.dump"
        dump.parent.mkdir(parents=True)
        environment = {**os.environ, "PGDATABASE": databases["source"]}
        subprocess.run([str(args.pg_bin / ("pg_dump.exe" if os.name == "nt" else "pg_dump")), "--format=custom", "--file", str(dump)], env=environment, check=True)
        for storage in ("public", "private", "artifacts"):
            original = workspace / "source" / storage
            shutil.copytree(original, workspace / "recovery" / storage)
            shutil.copytree(workspace / "recovery" / storage, workspace / "restored" / storage)
        environment["PGDATABASE"] = databases["restore"]
        subprocess.run([str(args.pg_bin / ("pg_restore.exe" if os.name == "nt" else "pg_restore")), "--exit-on-error", "--dbname", databases["restore"], str(dump)], env=environment, check=True)
        with psycopg.connect(dbname="postgres", autocommit=True) as operator:
            operator.execute(sql.SQL("GRANT secondhand_web TO {}").format(sql.Identifier(web_user)))
        environment["PGUSER"] = web_user
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--phase", "restore", "--workspace", str(workspace)], cwd=BASE, env=environment, check=True)
        source = json.loads((workspace / "source.json").read_text())
        evidence.update(json.loads((workspace / "search.json").read_text()))
        evidence["warm_scan"] = source["warm_scan"]
        evidence["restore"] = json.loads((workspace / "restore.json").read_text())
        evidence["restore"]["database_dump_sha256"] = sha256(dump)
        evidence["restore"]["file_counts"] = {key: len(value) for key, value in source["storage_manifests"].items()}
        print("Repeating actual dataset generation and model training", flush=True)
        evidence["reproducibility"] = reproduce_model(workspace)
        evidence["passed"] = all(evidence[key]["passed"] for key in ("search", "warm_scan", "restore", "reproducibility"))
    except Exception as exc:
        # Record failure class only; no credentials or private exception arguments in public evidence.
        evidence["passed"] = False
        evidence["failed_with"] = type(exc).__name__
        raise
    finally:
        write_json(args.output, evidence)
    print(json.dumps({"evidence": str(args.output), "passed": evidence["passed"]}), flush=True)
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
