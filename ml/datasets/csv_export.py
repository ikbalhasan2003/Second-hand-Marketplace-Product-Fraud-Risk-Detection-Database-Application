"""Privacy-bounded CSV projection of the existing validated frozen dataset."""
import csv
import io

from ml.contract import FEATURE_NAMES


def safe_cell(value):
    text = str(value) if value is not None else ""
    if text.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def dataset_csv(records, manifest):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    columns = ["dataset_version", "dataset_sha256", "export_cutoff", "record_key", "partition",
               "source_type", "label", "label_source", "label_decided_at", "feature_as_of", "is_synthetic",
               "category", "feature_schema", "source_attribution", "source_access_notes", "label_definition", *FEATURE_NAMES]
    writer.writerow(columns)
    for record in records:
        sources = [source for source in manifest.get("sources", []) if source["source_type"] == record.get("source_type")]
        provenance = {
            "source_attribution": "; ".join(source["attribution"] for source in sources),
            "source_access_notes": "; ".join(source["license_access_notes"] for source in sources),
            "label_definition": ("Simulated scenario label; not a real fraud finding" if record.get("is_synthetic") else
                "Evidence-backed canonical moderation decision; unresolved excluded"),
        }
        values = {**manifest, **record, **record["features"], **provenance}
        writer.writerow([safe_cell(values.get(key)) for key in columns])
    return output.getvalue().encode("utf-8-sig")
