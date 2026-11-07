"""Durable training on registered frozen data; never activates models automatically."""
import json
from datetime import datetime
import shutil
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ml.datasets.io import load_dataset, checksum

PIPELINE_VERSION = "marketplace-v1-rf-200-v1"


class TrainingFailure(ValueError):
    pass


def evaluate_candidate(report, configuration):
    for partition in ("validation", "test"):
        result = report["models"]["random_forest"][partition]["all"]
        if (result["sample_count"] < configuration["minimum_partition_samples"]
                or result["fraud_count"] in (0, result["sample_count"])):
            raise TrainingFailure("Evaluation needs at least 10 samples and both labels in validation and test; freeze more independent labeled groups.")
        if (result["precision"] < configuration["minimum_precision"]
                or result["recall"] < configuration["minimum_recall"]):
            raise TrainingFailure("Candidate failed the precision/recall gate (minimum 0.50 each); review labels and collect more representative data.")


def verified_dataset(root, snapshot):
    path = (root / snapshot["manifest_key"]).resolve()
    if not path.is_relative_to(root) or path.name != "manifest.json":
        raise TrainingFailure("Registered dataset path is invalid; register a new trusted frozen export.")
    try:
        records, manifest = load_dataset(path.parent)
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise TrainingFailure("Frozen dataset is missing, corrupt or incompatible; restore its verified files or freeze a new approved export.") from error
    if (manifest["dataset_sha256"] != snapshot["dataset_sha256"]
            or manifest["dataset_version"] != snapshot["version"]
            or ("seed" in snapshot and manifest["seed"] != snapshot["seed"])
            or ("export_cutoff" in snapshot and datetime.fromisoformat(manifest["export_cutoff"]) !=
                datetime.fromisoformat(snapshot["export_cutoff"]))):
        raise TrainingFailure("Dataset checksum/version mismatch; restore the frozen artifacts or create a new export.")
    for partition in ("train", "validation", "test"):
        selected = [r for r in records if r["partition"] == partition]
        if len(selected) < 10 or {r["label"] for r in selected} != {"fraud", "legitimate"}:
            raise TrainingFailure("Insufficient labeled data: require 10 samples and both labels in every train/validation/test partition. Freeze more independent labeled groups.")
    return path.parent, manifest


def register_candidate(cursor, job, directory, root, metadata, report):
    """Register the real fitted output against the existing immutable dataset (including real reviews)."""
    from ml.training.artifacts import load_trusted_pipeline
    from ml.contract import SCHEMA_VERSION
    load_trusted_pipeline(directory, metadata["artifact_key"], metadata["artifact_sha256"],
                          SCHEMA_VERSION, metadata["dependency_manifest"], metadata["class_mapping"])
    if checksum(directory / "evaluation.json") != metadata["evaluation_sha256"]:
        raise TrainingFailure("Candidate evaluation checksum mismatch; retry with trusted artifacts.")
    snapshot = job["configuration"]["dataset"]
    cursor.execute("SELECT set_config('app.actor_id',%s,true),set_config('app.action_reason',%s,true)",
                   (str(job["requested_by"]), f"Training job {job['job_id']} evaluation passed; manual activation required"))
    cursor.execute("""INSERT INTO risk_models(version,feature_schema_id,dataset_id,algorithm,artifact_key,
        artifact_sha256,seed,class_mapping,dependency_manifest,code_revision,registered_by)
        VALUES(%s,%s,%s,'random_forest',%s,%s,%s,%s,%s,%s,%s) RETURNING model_id""",
        (metadata["version"], snapshot["feature_schema_id"], job["dataset_id"],
         (directory / metadata["artifact_key"]).relative_to(root).as_posix(), metadata["artifact_sha256"],
         metadata["seed"], Jsonb(metadata["class_mapping"]), Jsonb(metadata["dependency_manifest"]),
         metadata["code_revision"], job["requested_by"]))
    model_id = cursor.fetchone()["model_id"]
    for partition, slices in report["models"]["random_forest"].items():
        for slice_key, result in slices.items():
            cm = result["confusion_matrix"]
            cursor.execute("""INSERT INTO model_evaluations(model_id,partition,slice_key,sample_count,fraud_count,
                true_positive,false_positive,true_negative,false_negative,average_precision,report_key)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (model_id, partition, slice_key, result["sample_count"], result["fraud_count"],
                 cm["true_positive"], cm["false_positive"], cm["true_negative"], cm["false_negative"],
                 result["average_precision"], (directory / "evaluation.json").relative_to(root).as_posix()))
    return model_id


def process_one(dsn, artifact_root):
    root = Path(artifact_root).resolve()
    # Session lock survives claim commit. Another trainer cannot recover a live trainer's job.
    # Connection/process death releases it; the next trainer recovers interrupted running jobs.
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(719241,9) AS acquired")
            if not cursor.fetchone()["acquired"]:
                return None
            cursor.execute("""UPDATE ai_training_jobs SET status='failed',error_code='interrupted',
                error_message='Trainer interrupted; automatic retry pending if attempts remain.',
                retry_at=clock_timestamp(),updated_at=clock_timestamp() WHERE status='running'""")
            cursor.execute("""UPDATE ai_training_jobs SET status='running',attempts=attempts+1,
                error_code=NULL,error_message=NULL,updated_at=clock_timestamp()
                WHERE job_id=(SELECT job_id FROM ai_training_jobs WHERE
                (status='queued' OR status='failed') AND attempts<3 AND retry_at<=clock_timestamp()
                ORDER BY job_id LIMIT 1) RETURNING *""")
            job = cursor.fetchone()
            if not job:
                return None
            if isinstance(job["configuration"], str):
                job["configuration"] = json.loads(job["configuration"])
            try:
                from ml.training.train import train, dependency_manifest, training_source_sha256
                if job["configuration"]["pipeline"] != PIPELINE_VERSION:
                    raise TrainingFailure("Worker pipeline version mismatch; deploy the compatible training worker.")
                dataset, manifest = verified_dataset(root, job["configuration"]["dataset"])
                directory = root / "training" / str(job["job_id"]) / str(job["attempts"])
                directory.mkdir(parents=True, exist_ok=False)
                snapshot = {"configuration": job["configuration"], "dependencies": dependency_manifest(),
                            "training_source_sha256": training_source_sha256(), "manifest": manifest}
                (directory / "snapshot.json").write_text(json.dumps(snapshot, sort_keys=True, indent=2), encoding="utf-8")
                # Keep exact input bytes and training source alongside each attempt.
                frozen_input = directory / "dataset"
                frozen_input.mkdir()
                for name in ("manifest.json", "records.jsonl"):
                    shutil.copyfile(dataset / name, frozen_input / name)
                package = Path(__file__).resolve().parents[1]
                for source in package.rglob("*.py"):
                    destination = directory / "source" / "ml" / source.relative_to(package)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                model_dir = directory / "model"
                metadata = train(frozen_input, model_dir, f"auto-job-{job['job_id']}-attempt-{job['attempts']}")
                report = json.loads((model_dir / "evaluation.json").read_text(encoding="utf-8"))
                checksums = {path.relative_to(directory).as_posix(): checksum(path)
                             for path in sorted(directory.rglob("*")) if path.is_file()}
                (directory / "checksums.json").write_text(json.dumps(checksums, sort_keys=True, indent=2), encoding="utf-8")
                evaluate_candidate(report, job["configuration"])
                with connection.transaction():
                    model_id = register_candidate(cursor, job, model_dir, root, metadata, report)
                    cursor.execute("UPDATE ai_training_jobs SET status='succeeded',model_id=%s,updated_at=clock_timestamp() WHERE job_id=%s", (model_id, job["job_id"]))
                    cursor.execute("""INSERT INTO admin_audit_logs(admin_id,action_type,dataset_id,model_id,reason,after_data)
                        VALUES(%s,'ai_training_succeeded',%s,%s,%s,%s)""", (job["requested_by"], job["dataset_id"], model_id,
                        "Candidate passed evaluation; explicit activation required", Jsonb({"job_id": job["job_id"],
                        "source_audit_id": job["source_audit_id"], "artifact_sha256": metadata["artifact_sha256"],
                        "snapshot_sha256": checksum(directory / "snapshot.json"),
                        "checksums_sha256": checksum(directory / "checksums.json")})))
                return {"job_id": job["job_id"], "status": "succeeded"}
            except Exception as error:
                # Never persist raw dependency, database, filesystem or training exception text.
                if isinstance(error, TrainingFailure):
                    message, code = str(error), "data_or_evaluation"
                elif isinstance(error, ImportError):
                    message, code = "Install the pinned training dependencies in the worker environment, then retry.", "dependencies"
                else:
                    message, code = "Training failed. Check worker credentials, frozen artifacts and compatible dependencies; retries stop after three attempts.", "training_failed"
                with connection.transaction():
                    cursor.execute("""UPDATE ai_training_jobs SET status='failed',error_code=%s,error_message=%s,
                        retry_at=clock_timestamp()+(attempts * interval '1 minute'),updated_at=clock_timestamp()
                        WHERE job_id=%s""", (code, message, job["job_id"]))
                    cursor.execute("""INSERT INTO admin_audit_logs(admin_id,action_type,dataset_id,reason,after_data)
                        VALUES(%s,'ai_training_failed',%s,'Background training attempt failed',%s)""",
                        (job["requested_by"], job["dataset_id"], Jsonb({"job_id": job["job_id"], "attempt": job["attempts"],
                         "source_audit_id": job["source_audit_id"], "error_code": code})))
                return {"job_id": job["job_id"], "status": "failed"}
