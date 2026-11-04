"""Consistent PostgreSQL extraction for the immutable marketplace-v1 contract."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from statistics import median

from psycopg.rows import dict_row

from ml.contract import SCHEMA_SHA256, SCHEMA_VERSION, keyword_count, normalize_text, text_fingerprint, validate_features


def extract_snapshot(connection, product_id: int, revision_no: int):
    """Extract only now, from one repeatable-read snapshot; never reconstruct old profiles."""
    with connection.transaction():
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT statement_timestamp() AS cutoff")
            as_of = cursor.fetchone()["cutoff"]
            cursor.execute("""SELECT r.*,p.seller_id,p.first_published_at,u.created_at AS seller_created_at,u.location AS seller_location
                              FROM product_revisions r JOIN products p USING(product_id) JOIN users u ON u.user_id=p.seller_id
                              WHERE r.product_id=%s AND r.revision_no=%s""", (product_id, revision_no))
            target = cursor.fetchone()
            if not target or target["created_at"] >= as_of or target["seller_created_at"] >= as_of:
                raise ValueError("Invalid target or seller chronology")
            latest_sql = """SELECT DISTINCT ON(r.product_id) r.*,p.seller_id,p.first_published_at
                            FROM product_revisions r JOIN products p USING(product_id)
                            WHERE r.created_at<%s AND p.first_published_at<%s
                            ORDER BY r.product_id,r.created_at DESC,r.revision_no DESC"""
            cursor.execute("""SELECT * FROM (""" + latest_sql + """) q WHERE product_id<>%s AND first_published_at>=%s
                              AND category_id=%s AND condition=%s AND currency=%s ORDER BY product_id""",
                           (as_of, as_of, product_id, as_of - timedelta(days=90), target["category_id"], target["condition"], target["currency"]))
            references = cursor.fetchall()
            if any(not row["price"].is_finite() or row["price"] <= 0 for row in references):
                raise ValueError("Invalid comparable price")
            reference_median = median([row["price"] for row in references]) if len(references) >= 15 else None
            cursor.execute("""SELECT * FROM (""" + latest_sql + """) q WHERE seller_id=%s AND product_id<>%s AND first_published_at>=%s ORDER BY product_id""",
                           (as_of, as_of, target["seller_id"], product_id, as_of - timedelta(days=30)))
            same_seller = cursor.fetchall()
            fingerprint = text_fingerprint(target["title"], target["description"])
            duplicates = [row for row in same_seller if text_fingerprint(row["title"], row["description"]) == fingerprint]
            cursor.execute("""SELECT product_id,first_published_at FROM products WHERE seller_id=%s
                              AND first_published_at>=%s AND first_published_at<%s ORDER BY product_id""",
                           (target["seller_id"], as_of - timedelta(days=7), as_of))
            postings = cursor.fetchall()
            cursor.execute("""SELECT r.review_id,r.product_id,r.revision_no,r.reviewed_at FROM
                              (SELECT DISTINCT ON(product_id,revision_no) * FROM moderation_reviews WHERE reviewed_at<%s
                               ORDER BY product_id,revision_no,reviewed_at DESC,review_id DESC) r
                              JOIN products p USING(product_id) WHERE p.seller_id=%s AND p.product_id<>%s
                              AND r.verdict='fraud' AND length(btrim(r.reason))>0 AND length(btrim(r.evidence_summary))>0
                              ORDER BY r.product_id,r.revision_no""", (as_of, target["seller_id"], product_id))
            reviews = cursor.fetchall()
            cursor.execute("SELECT image_id,uploaded_at FROM product_images WHERE product_id=%s AND revision_no=%s ORDER BY image_id", (product_id, revision_no))
            images = cursor.fetchall()
            if len(images) > 6 or any(row["uploaded_at"] >= as_of for row in images):
                raise ValueError("Invalid target image chronology")
            seller_location = normalize_text(target["seller_location"] or "")
            listing_location = normalize_text(target["location"] or "")
            location_missing = not seller_location or not listing_location
            features = {
                "price_ratio": float(Decimal(target["price"]) / reference_median) if reference_median is not None else None,
                "comparable_count": len(references), "price_baseline_missing": int(reference_median is None),
                "keyword_count": keyword_count(target["title"], target["description"]),
                "seller_age_days": (as_of - target["seller_created_at"]).total_seconds() / 86400,
                "prior_confirmed_fraud_count": len({row["product_id"] for row in reviews}),
                "posting_frequency_7d": len(postings), "image_count": len(images),
                "location_difference": None if location_missing else int(seller_location != listing_location),
                "location_missing": int(bool(location_missing)), "duplicate_text_count_30d": len(duplicates),
            }
            validate_features(features)
            source_times = [target["created_at"], target["seller_created_at"]]
            source_times += [row["created_at"] for row in references + same_seller]
            source_times += [row["first_published_at"] for row in references + same_seller + postings]
            source_times += [row["reviewed_at"] for row in reviews] + [row["uploaded_at"] for row in images]
            evidence = {
                "cutoff": as_of.isoformat(), "target": {"product_id": product_id, "revision_no": revision_no},
                "schema_sha256": SCHEMA_SHA256, "normalization_version": SCHEMA_VERSION,
                "seller_location_observed": target["seller_location"], "listing_location": target["location"],
                "seller_location_observed_at": as_of.isoformat(),
                "reference_median": str(reference_median) if reference_median is not None else None,
                "references": [{"product_id": r["product_id"], "revision_no": r["revision_no"], "price": str(r["price"])} for r in references],
                "prior_reviews": [{"review_id": r["review_id"], "product_id": r["product_id"], "revision_no": r["revision_no"]} for r in reviews],
                "publication_products": [r["product_id"] for r in postings],
                "duplicate_products": [{"product_id": r["product_id"], "revision_no": r["revision_no"]} for r in duplicates],
                "windows": {"price_start": (as_of - timedelta(days=90)).isoformat(), "posting_start": (as_of - timedelta(days=7)).isoformat(), "duplicate_start": (as_of - timedelta(days=30)).isoformat()},
            }
            snapshot = {"schema_version": SCHEMA_VERSION, "features": features, "evidence": evidence,
                        "feature_evidence": {"latest_source_at": max(source_times).isoformat(), "point_in_time_snapshot": True}}
    return as_of, snapshot
