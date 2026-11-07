"""Keep disposable test files in a fresh workspace directory on restricted Windows hosts."""
from pathlib import Path
from uuid import uuid4

import pytest


def pytest_configure(config):
    if not config.option.basetemp:
        config.option.basetemp = str(Path(__file__).resolve().parents[1] / ".local" / f"pytest-{uuid4().hex}")


@pytest.fixture(scope="session")
def scan_artifact(tmp_path_factory):
    from ml.datasets.generate import generate_records
    from ml.datasets.io import write_dataset
    from ml.training.train import train
    root = tmp_path_factory.mktemp("publication-model")
    write_dataset(root / "dataset", generate_records(300, 42), {
        "dataset_version": "publication-test", "generator_version": "scenario-v1", "seed": 42,
        "export_cutoff": "2026-12-31T00:00:00+00:00", "split_strategy": "connected groups",
        "limitations": ["Synthetic integration fixture only"],
        "sources": [{"source_type": "synthetic", "attribution": "Project test fixture",
                     "license_access_notes": "No personal data"}],
    })
    train(root / "dataset", root / "model", "publication-test-rf")
    return root


@pytest.fixture
def scan_listing(scan_artifact, db):
    """Real fitted inference on the test transaction's connection, with real fenced SQL writes."""
    import json
    import math
    from django.db import connection
    from accounts.models import User
    from django.contrib.auth.models import Group
    from marketplace.db import actor_transaction, one, rows
    from ml.training.register import register
    from ml.training.artifacts import load_trusted_pipeline
    from ml.training.preprocessing import matrix
    from risk.features import extract_snapshot_cursor
    from psycopg.rows import dict_row
    from risk.worker import observed_factors
    # Transactional race tests may flush managed auth rows between fixtures.
    # SQL-owned categories/configuration remain; rebuild only test memberships.
    for role in ("buyer", "seller", "administrator"):
        Group.objects.get_or_create(name=role)
    admin = User.objects.filter(groups__name="administrator").first()
    if not admin:
        admin = User.objects.create_user("scan-operator@example.invalid", full_name="Synthetic scan operator")
        admin.groups.add(Group.objects.get(name="administrator"))
    identifiers = register(connection.connection, scan_artifact / "dataset", scan_artifact / "model",
                           scan_artifact, admin.pk, "Register synthetic publication verification artifact")
    with actor_transaction(admin, "Activate synthetic publication verification artifact"):
        rows("SELECT activate_risk_configuration(%s,%s)", [identifiers["model_id"], identifiers["ruleset_id"]])
    model = one("SELECT * FROM risk_models WHERE model_id=%s", [identifiers["model_id"]])
    from ml.contract import SCHEMA_VERSION
    pipeline = load_trusted_pipeline(scan_artifact, model["artifact_key"], model["artifact_sha256"],
                                     SCHEMA_VERSION, model["dependency_manifest"], model["class_mapping"])

    def complete(job):
        with connection.connection.cursor(row_factory=dict_row) as cursor:
            as_of, snapshot = extract_snapshot_cursor(cursor, job["product_id"], job["revision_no"])
        rows("SELECT save_risk_snapshot(%s,%s,%s,%s::jsonb)",
             [job["job_id"], job["claim_token"], as_of, json.dumps(snapshot)])
        probability = float(pipeline.predict_proba(matrix([snapshot]))[0, list(pipeline.classes_).index(model["class_mapping"]["fraud"])])
        rows("SELECT complete_risk_job(%s,%s,%s,%s::jsonb,NULL)",
             [job["job_id"], job["claim_token"], math.floor(probability * 100 + 0.5),
              json.dumps(observed_factors(snapshot["features"]))])

    def scan(product_id):
        while True:
            job = one("SELECT * FROM claim_risk_job(interval '2 minutes')")
            if not job:
                break
            complete(job)
        return one("SELECT * FROM current_listing_risk WHERE product_id=%s", [product_id])
    scan.complete = complete
    return scan
