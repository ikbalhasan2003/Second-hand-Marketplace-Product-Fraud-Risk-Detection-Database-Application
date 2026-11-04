"""Reproducible simulated scenarios; not measured marketplace fraud outcomes."""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ml.contract import GENERATOR_VERSION, SCHEMA_VERSION
from ml.datasets.io import write_dataset
from ml.datasets.split import assign_partitions

CATEGORIES = ("electronics", "furniture", "clothing", "sports", "books")


def generate_records(count: int = 5000, seed: int = 20261104) -> list[dict]:
    if count < 60:
        raise ValueError("At least sixty records are needed for grouped partitions")
    rng = random.Random(seed)
    anchor = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = []
    # Each family connects two seller groups. Families never span scenario components.
    for index in range(count):
        seller = index // 10
        family = seller // 2
        intent = rng.random() < 0.24
        # Labels describe a latent simulated scenario, with deliberately overlapping signals.
        adverse = intent if rng.random() > 0.12 else not intent
        missing_price = rng.random() < 0.13
        missing_location = rng.random() < 0.09
        features = {
            "price_ratio": None if missing_price else round(max(0.08, rng.gauss(0.68 if adverse else 0.95, 0.28)), 6),
            "comparable_count": rng.randrange(15) if missing_price else rng.randrange(15, 150),
            "price_baseline_missing": int(missing_price),
            "keyword_count": min(8, max(0, int(rng.gauss(2.0 if adverse else 0.7, 1.2)))),
            "seller_age_days": round(rng.expovariate(1 / (95 if adverse else 280)), 6),
            "prior_confirmed_fraud_count": int(rng.random() < (0.28 if adverse else 0.04)),
            "posting_frequency_7d": max(0, int(rng.gauss(9 if adverse else 4, 4))),
            "image_count": rng.randrange(0, 7) if adverse else rng.randrange(1, 7),
            "location_difference": None if missing_location else int(rng.random() < (0.45 if adverse else 0.2)),
            "location_missing": int(missing_location),
            "duplicate_text_count_30d": max(0, int(rng.gauss(3 if adverse else 0.6, 1.6))),
        }
        as_of = anchor + timedelta(days=index % 250, minutes=index)
        records.append({
            "record_key": f"synthetic-{index:07d}", "seller_group_key": f"seller-{seller:05d}",
            "template_family_key": f"scenario-component-{family:05d}",
            "duplicate_group_key": f"variant-{seller:05d}-{index % 3}",
            "feature_schema": SCHEMA_VERSION, "feature_as_of": as_of.isoformat(), "features": features,
            "feature_evidence": {"latest_source_at": (as_of - timedelta(seconds=1)).isoformat(), "point_in_time_snapshot": True},
            "label": "fraud" if intent else "legitimate", "label_source": "simulated-latent-scenario",
            "label_decided_at": (as_of + timedelta(days=3)).isoformat(), "source_type": "synthetic",
            "is_synthetic": True, "scenario_version": GENERATOR_VERSION,
            "category": CATEGORIES[index % len(CATEGORIES)], "partition": "train",
        })
    assign_partitions(records, seed)
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261104)
    args = parser.parse_args(argv)
    records = generate_records(args.count, args.seed)
    manifest = write_dataset(args.output, records, {
        "dataset_version": f"synthetic-{GENERATOR_VERSION}-{args.seed}-{args.count}",
        "generator_version": GENERATOR_VERSION, "seed": args.seed,
        "export_cutoff": "2026-12-31T00:00:00+00:00",
        "split_strategy": "connected seller/template/duplicate components; seeded approximate 70/15/15",
        "sources": [{"source_type": "synthetic", "attribution": "Project-authored noisy latent scenarios",
                     "license_access_notes": "Generated for this project; no external or personal data"}],
        "limitations": ["Synthetic-only prototype; no real-world fraud accuracy claim",
                        "Aggregates are simulated point-in-time summaries, not observations of real people",
                        "No independently authored challenge dataset is available"],
    })
    print(f"Wrote {manifest['record_count']} simulated records; SHA256={manifest['dataset_sha256']}")


if __name__ == "__main__":
    main()
