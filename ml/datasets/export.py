"""Export a frozen, administrator-approved dataset using the training read-only role."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ml.contract import SCHEMA_SHA256, SCHEMA_VERSION
from ml.datasets.io import write_dataset


def export_frozen_dataset(connection, version: str, output: Path) -> dict:
    """No live profile, contacts, chats or attachments are queried.

    Admin registration must supply frozen feature_values containing only `features`
    and safe `feature_evidence` chronology metadata. Earlier incomplete datasets fail.
    """
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("""
                SELECT d.dataset_id,d.version,d.generator_version,d.seed,d.export_cutoff,
                       d.split_strategy,f.version,f.definition
                FROM dataset_versions d JOIN feature_schemas f USING(feature_schema_id)
                WHERE d.version=%s AND d.state='frozen'
            """, (version,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Dataset must exist and be frozen by an authorized administrator")
            dataset_id, version, generator, seed, cutoff, strategy, schema, definition = row
            if schema != SCHEMA_VERSION or definition.get("schema_sha256") != SCHEMA_SHA256:
                raise ValueError("Frozen dataset has an incompatible feature contract")
            cursor.execute("""
                SELECT r.record_key,r.seller_group_key,r.template_family_key,r.duplicate_group_key,
                       r.feature_as_of,r.feature_values,r.label,r.label_source,r.label_decided_at,
                       r.is_synthetic,r.scenario_version,g.partition,s.source_type,s.source_key,
                       s.attribution,s.license_access_notes
                FROM dataset_records r JOIN dataset_split_groups g
                  ON (g.dataset_id,g.split_group_id)=(r.dataset_id,r.split_group_id)
                JOIN dataset_sources s USING(source_id)
                WHERE r.dataset_id=%s ORDER BY r.record_key
            """, (dataset_id,))
            records = []
            sources = {}
            for r in cursor.fetchall():
                (key, seller, template, duplicate, as_of, values, label, label_source, decided,
                 synthetic, scenario, partition, source_type, source_key, attribution, license_notes) = r
                if set(values) != {"features", "feature_evidence", "category"}:
                    raise ValueError("Export requires a frozen predictor snapshot and safe chronology metadata")
                records.append({
                    "record_key": key, "seller_group_key": seller, "template_family_key": template,
                    "duplicate_group_key": duplicate, "feature_schema": schema,
                    "feature_as_of": as_of.isoformat(), "features": values["features"],
                    "feature_evidence": values["feature_evidence"], "label": label,
                    "label_source": label_source, "label_decided_at": decided.isoformat(),
                    "source_type": source_type, "is_synthetic": synthetic, "scenario_version": scenario,
                    "category": values["category"], "partition": partition,
                })
                sources[source_key] = {"source_type": source_type, "attribution": attribution, "license_access_notes": license_notes}
    if not records:
        raise ValueError("Frozen dataset has no eligible records")
    return write_dataset(output, records, {
        "dataset_version": version, "generator_version": generator, "seed": seed,
        "export_cutoff": cutoff.isoformat(), "split_strategy": strategy,
        "sources": list(sources.values()),
        "limitations": ["Review-backed project data may be selected and small; no population accuracy claim",
                        "Export requires pre-frozen point-in-time predictors; mutable historical profiles are never reconstructed"],
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    import psycopg

    with psycopg.connect(os.environ["TRAINING_DATABASE_URL"]) as connection:
        manifest = export_frozen_dataset(connection, args.dataset_version, args.output)
    print(f"Exported {manifest['record_count']} approved rows; SHA256={manifest['dataset_sha256']}")


if __name__ == "__main__":
    main()
