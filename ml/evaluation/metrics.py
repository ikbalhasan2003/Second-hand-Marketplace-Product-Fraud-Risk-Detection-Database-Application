"""Fraud-positive metrics with sample counts and explicit source/category slices."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support


def measure(records, probabilities, threshold=0.5):
    labels = np.asarray([int(row["label"] == "fraud") for row in records])
    probabilities = np.asarray(probabilities, dtype=float)
    predicted = probabilities >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(labels, predicted, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    return {
        "sample_count": len(records), "fraud_count": int(labels.sum()),
        "fraud_prevalence": float(labels.mean()), "threshold": threshold,
        "precision": float(precision), "recall": float(recall), "f1": float(f1),
        "average_precision": float(average_precision_score(labels, probabilities)) if labels.any() else None,
        "confusion_matrix": {"true_negative": int(tn), "false_positive": int(fp), "false_negative": int(fn), "true_positive": int(tp)},
        "false_positive_examples": [
            {"record_key": row["record_key"], "probability": float(probability), "category": row["category"]}
            for row, probability, expected, actual in zip(records, probabilities, labels, predicted, strict=True)
            if not expected and actual
        ][:10],
    }


def sliced_metrics(records, probabilities):
    probabilities = np.asarray(probabilities)
    result = {"all": measure(records, probabilities)}
    for attribute in ("source_type", "category"):
        for value in sorted({row[attribute] for row in records}):
            indices = [i for i, row in enumerate(records) if row[attribute] == value]
            result[f"{attribute}:{value}"] = measure([records[i] for i in indices], probabilities[indices])
    return result
