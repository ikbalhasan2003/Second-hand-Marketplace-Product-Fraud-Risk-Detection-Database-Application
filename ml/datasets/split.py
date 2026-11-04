"""Connected seller/template/duplicate components stay in one evaluation partition."""

from __future__ import annotations

import random


def assign_partitions(records: list[dict], seed: int) -> None:
    parents = list(range(len(records)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    seen = {}
    for index, record in enumerate(records):
        if record.get("partition") == "challenge":
            continue
        for name in ("seller_group_key", "template_family_key", "duplicate_group_key"):
            value = record.get(name)
            if value:
                key = (name, value)
                if key in seen:
                    parents[find(index)] = find(seen[key])
                seen[key] = index
    components = {}
    for index, record in enumerate(records):
        if record.get("partition") != "challenge":
            components.setdefault(find(index), []).append(index)
    grouped = sorted(components.values(), key=lambda indices: min(records[i]["record_key"] for i in indices))
    random.Random(seed).shuffle(grouped)
    total = sum(map(len, grouped))
    counts = {"train": 0, "validation": 0, "test": 0}
    targets = {"train": total * 0.7, "validation": total * 0.15, "test": total * 0.15}
    for component in grouped:
        partition = max(counts, key=lambda key: (targets[key] - counts[key]) / max(targets[key], 1))
        for index in component:
            records[index]["partition"] = partition
        counts[partition] += len(component)
    # Challenge overlap is rejected by validate_partitions rather than silently reassigned.
