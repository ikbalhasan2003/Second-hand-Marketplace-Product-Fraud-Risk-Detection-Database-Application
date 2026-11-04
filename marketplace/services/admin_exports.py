"""Audited reviewed exports reuse immutable worker snapshots; no profile reconstruction."""
import hashlib
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone
from psycopg.types.json import Jsonb

from marketplace.db import actor_transaction, one, rows
from marketplace.services.moderation import require_admin, reason_text
from ml.contract import SCHEMA_SHA256, SCHEMA_VERSION, validate_record
from ml.datasets.io import write_dataset
from ml.datasets.split import assign_partitions


def reviewed_candidates(cutoff):
    schema = one("SELECT * FROM feature_schemas WHERE version=%s", [SCHEMA_VERSION])
    if not schema or schema["definition"].get("schema_sha256") != SCHEMA_SHA256:
        return None, [], {"unresolved": 0, "missing_snapshot": 0}
    result = rows("""SELECT r.*,p.seller_id,v.text_fingerprint,c.name AS category,j.job_id,j.feature_as_of,j.feature_snapshot
        FROM effective_reviews_at(%s) r JOIN products p USING(product_id)
        JOIN product_revisions v USING(product_id,revision_no) JOIN categories c USING(category_id)
        LEFT JOIN LATERAL (SELECT * FROM risk_scan_jobs j WHERE j.product_id=r.product_id AND j.revision_no=r.revision_no
            AND j.feature_schema_id=%s AND j.feature_as_of<=r.reviewed_at AND j.feature_as_of<=%s
            AND j.feature_snapshot IS NOT NULL ORDER BY j.feature_as_of DESC,j.job_id DESC LIMIT 1) j ON true
        ORDER BY r.review_id""", [cutoff, schema["feature_schema_id"], cutoff])
    excluded = {"unresolved": 0, "missing_snapshot": 0}
    candidates = []
    for item in result:
        if item["verdict"] not in ("fraud", "legitimate") or not item["evidence_summary"].strip():
            excluded["unresolved"] += 1
            continue
        snapshot = item["feature_snapshot"] or {}
        if snapshot.get("schema_version") != SCHEMA_VERSION or not snapshot.get("feature_evidence"):
            excluded["missing_snapshot"] += 1
            continue
        record = {
            "record_key": hashlib.sha256(f"review:{item['review_id']}".encode()).hexdigest(),
            "seller_group_key": hashlib.sha256(f"seller:{item['seller_id']}".encode()).hexdigest(),
            "template_family_key": None, "duplicate_group_key": item["text_fingerprint"],
            "feature_schema": SCHEMA_VERSION, "feature_as_of": item["feature_as_of"].isoformat(),
            "features": snapshot.get("features"), "feature_evidence": snapshot["feature_evidence"],
            "label": item["verdict"], "label_source": "moderation_review", "label_decided_at": item["reviewed_at"].isoformat(),
            "source_type": "project_review", "is_synthetic": False, "scenario_version": None,
            "category": item["category"], "partition": "train",
        }
        try:
            validate_record(record, cutoff.isoformat())
        except (ValueError, TypeError, KeyError):
            excluded["missing_snapshot"] += 1
            continue
        candidates.append((record, {"review_id": item["review_id"], "job_id": item["job_id"], "category": item["category"]}))
    return schema, candidates, excluded


def create_reviewed_export(user, version, cutoff, seed, reason):
    require_admin(user)
    reason = reason_text(reason)
    if cutoff > timezone.now():
        raise ValidationError("The export cutoff cannot be in the future.")
    root = settings.ARTIFACT_ROOT.resolve()
    target = root / "exports" / str(uuid.uuid4())
    created = False
    try:
        with actor_transaction(user, reason):
            # The cutoff is immutable; registration rechecks canonical labels and snapshot identity.
            schema, candidates, _ = reviewed_candidates(cutoff)
            if not schema or not candidates:
                raise ValidationError("No compatible evidence-backed labels with frozen point-in-time features are eligible at this cutoff.")
            records = [record for record, _ in candidates]
            assign_partitions(records, seed)
            created = True
            manifest = write_dataset(target, records, {
                "dataset_version": version, "generator_version": None, "seed": seed,
                "export_cutoff": cutoff.isoformat(),
                "split_strategy": "Connected seller and normalized-text duplicate components; deterministic 70/15/15 grouped allocation",
                "sources": [{"source_type": "project_review", "attribution": "Project evidence-backed canonical moderation decisions",
                             "license_access_notes": "Administrator-approved course research; no private contacts, chats or attachments"}],
                "limitations": ["Reviewed course records are selected and may be small; no population accuracy claim", "Only existing point-in-time snapshots are eligible; missing history is excluded"],
            })
            data = [{**item, "partition": record["partition"]} for record, item in candidates]
            with connection.cursor() as cursor:
                cursor.execute("SELECT app_register_reviewed_export(%s,%s,%s,%s,%s,%s,%s)", [version, cutoff, seed,
                    schema["feature_schema_id"], (target / "manifest.json").relative_to(root).as_posix(), manifest["dataset_sha256"], Jsonb(data)])
                dataset_id = cursor.fetchone()[0]
        return dataset_id
    except Exception:
        if created:
            # Only remove the two known newly generated files, within the trusted export root.
            resolved = target.resolve()
            if resolved.is_relative_to(root / "exports"):
                for name in ("records.jsonl", "manifest.json"):
                    (resolved / name).unlink(missing_ok=True)
                if resolved.is_dir():
                    resolved.rmdir()
        raise
