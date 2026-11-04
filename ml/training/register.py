"""Trusted operator registration of project-produced datasets and fitted models."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from psycopg.types.json import Jsonb

from ml.contract import SCHEMA_DEFINITION, SCHEMA_SHA256, SCHEMA_VERSION
from ml.datasets.io import checksum, load_dataset
from ml.training.artifacts import load_trusted_pipeline


def register(connection, dataset: Path, model: Path, artifact_root: Path, admin_id: int, reason: str) -> dict:
    """Requires owner/operator credentials; runtime web/worker roles cannot register bytes."""
    if not reason.strip():
        raise ValueError("A registration reason is required")
    dataset, model, artifact_root = Path(dataset).resolve(), Path(model).resolve(), Path(artifact_root).resolve()
    if not dataset.is_relative_to(artifact_root) or not model.is_relative_to(artifact_root):
        raise ValueError("Dataset and model must be within the trusted artifact root")
    records, manifest = load_dataset(dataset)
    metadata = json.loads((model / "model.json").read_text(encoding="utf-8"))
    if (metadata["dataset_sha256"] != manifest["dataset_sha256"] or metadata["dataset_version"] != manifest["dataset_version"]
            or metadata["feature_schema_sha256"] != SCHEMA_SHA256):
        raise ValueError("Model training dataset or feature definition mismatch")
    report_path = model / "evaluation.json"
    if checksum(report_path) != metadata["evaluation_sha256"]:
        raise ValueError("Evaluation report checksum mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("Evaluation dataset mismatch")
    load_trusted_pipeline(model, metadata["artifact_key"], metadata["artifact_sha256"], metadata["feature_schema"], metadata["dependency_manifest"], metadata["class_mapping"])
    schema_definition = {**SCHEMA_DEFINITION, "schema_sha256": SCHEMA_SHA256}
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.actor_id',%s,true),set_config('app.action_reason',%s,true)", (str(admin_id), reason))
            cursor.execute("SELECT require_admin_actor()")
            cursor.execute("SELECT feature_schema_id,definition FROM feature_schemas WHERE version=%s", (SCHEMA_VERSION,))
            found = cursor.fetchone()
            if found:
                schema_id, definition = found
                if definition != schema_definition:
                    raise ValueError("Registered feature-schema version has different immutable semantics")
            else:
                cursor.execute("INSERT INTO feature_schemas(version,definition,code_revision) VALUES(%s,%s,%s) RETURNING feature_schema_id", (SCHEMA_VERSION, Jsonb(schema_definition), metadata["code_revision"]))
                schema_id = cursor.fetchone()[0]
            cursor.execute("""INSERT INTO dataset_versions(version,feature_schema_id,generator_version,seed,export_cutoff,split_strategy,created_by)
                              VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING dataset_id""",
                           (manifest["dataset_version"], schema_id, manifest.get("generator_version"), manifest["seed"], manifest["export_cutoff"], manifest["split_strategy"], admin_id))
            dataset_id = cursor.fetchone()[0]
            source_ids = {}
            for source_type in sorted({record["source_type"] for record in records}):
                sources = [source for source in manifest["sources"] if source["source_type"] == source_type]
                if len(sources) != 1:
                    raise ValueError("Each source type requires one unambiguous provenance entry in this format")
                source = sources[0]
                source_key = "registered-" + hashlib.sha256(f"{manifest['dataset_version']}:{source_type}".encode()).hexdigest()
                cursor.execute("""INSERT INTO dataset_sources(source_key,source_type,attribution,license_access_notes)
                                  VALUES(%s,%s,%s,%s) RETURNING source_id""", (source_key, source_type, source["attribution"], source["license_access_notes"]))
                source_ids[source_type] = cursor.fetchone()[0]
            # Multiple connected components may share a split, but no component crosses it.
            groups = {}
            for record in records:
                key = (record["seller_group_key"], record["partition"])
                if key not in groups:
                    cursor.execute("INSERT INTO dataset_split_groups(dataset_id,group_key,partition) VALUES(%s,%s,%s) RETURNING split_group_id", (dataset_id, key[0], key[1]))
                    groups[key] = cursor.fetchone()[0]
            rows = []
            for record in records:
                if not record["is_synthetic"]:
                    # A live review link is mandatory for project labels; this format deliberately
                    # has no private internal IDs. Use the audited review exporter to register them.
                    raise ValueError("This operator importer registers synthetic records only; real reviews require canonical review linkage")
                values = {"features": record["features"], "feature_evidence": record["feature_evidence"], "category": record["category"]}
                rows.append((dataset_id, record["record_key"], source_ids[record["source_type"]], groups[(record["seller_group_key"], record["partition"])], record["seller_group_key"], record["template_family_key"], record["duplicate_group_key"], record["feature_as_of"], Jsonb(values), record["label"], record["label_source"], record["label_decided_at"], record["is_synthetic"], record["scenario_version"]))
            cursor.executemany("""INSERT INTO dataset_records(dataset_id,record_key,source_id,split_group_id,seller_group_key,template_family_key,duplicate_group_key,
                                  feature_as_of,feature_values,label,label_source,label_decided_at,is_synthetic,scenario_version)
                                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
            cursor.execute("UPDATE dataset_versions SET state='frozen',manifest_key=%s,dataset_sha256=%s,frozen_at=clock_timestamp() WHERE dataset_id=%s", ((dataset / "manifest.json").relative_to(artifact_root).as_posix(), manifest["dataset_sha256"], dataset_id))
            artifact_key = (model / metadata["artifact_key"]).relative_to(artifact_root).as_posix()
            cursor.execute("""INSERT INTO risk_models(version,feature_schema_id,dataset_id,algorithm,artifact_key,artifact_sha256,seed,class_mapping,dependency_manifest,code_revision,registered_by)
                              VALUES(%s,%s,%s,'random_forest',%s,%s,%s,%s,%s,%s,%s) RETURNING model_id""",
                           (metadata["version"], schema_id, dataset_id, artifact_key, metadata["artifact_sha256"], metadata["seed"], Jsonb(metadata["class_mapping"]), Jsonb(metadata["dependency_manifest"]), metadata["code_revision"], admin_id))
            model_id = cursor.fetchone()[0]
            for partition, slices in report["models"]["random_forest"].items():
                for slice_key, result in slices.items():
                    cm = result["confusion_matrix"]
                    cursor.execute("""INSERT INTO model_evaluations(model_id,partition,slice_key,sample_count,fraud_count,true_positive,false_positive,true_negative,false_negative,average_precision,report_key)
                                      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                   (model_id, partition, slice_key, result["sample_count"], result["fraud_count"], cm["true_positive"], cm["false_positive"], cm["true_negative"], cm["false_negative"], result["average_precision"], report_path.relative_to(artifact_root).as_posix()))
            cursor.execute("INSERT INTO risk_rulesets(version,feature_schema_id,created_by) VALUES(%s,%s,%s) RETURNING ruleset_id", (metadata["version"] + "-rules", schema_id, admin_id))
            ruleset_id = cursor.fetchone()[0]
            cursor.executemany("INSERT INTO risk_rules(ruleset_id,rule_key,numeric_value,description) VALUES(%s,%s,%s,%s)", [(ruleset_id, "medium_min", 40, "Initial course-demo medium-risk lower bound"), (ruleset_id, "high_min", 75, "Initial course-demo high-risk lower bound")])
            cursor.execute("INSERT INTO admin_audit_logs(admin_id,action_type,model_id,reason,after_data) VALUES(%s,'model_registration',%s,%s,%s)", (admin_id, model_id, reason, Jsonb({"artifact_sha256": metadata["artifact_sha256"], "dataset_sha256": manifest["dataset_sha256"], "synthetic_only": metadata["synthetic_only"]})))
    return {"dataset_id": dataset_id, "model_id": model_id, "ruleset_id": ruleset_id}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--admin-id", type=int, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    import psycopg

    with psycopg.connect(os.environ["REGISTRATION_DATABASE_URL"]) as connection:
        print(json.dumps(register(connection, args.dataset, args.model, args.artifact_root, args.admin_id, args.reason)))


if __name__ == "__main__":
    main()
