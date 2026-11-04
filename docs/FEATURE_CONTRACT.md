# Feature contract: marketplace-v1

Decision date: 4 November 2026. This is the normative first P0 feature schema. The schema version, its complete canonical definition and SHA-256 must accompany datasets, models and runtime snapshots. The reference database stores this contract but does not itself calculate the features. Implementations and measured verification are recorded separately.

## Time and source boundary

`feature_as_of` is an aware UTC instant captured from PostgreSQL at the start of a consistent read snapshot. Use a repeatable-read transaction for all extraction queries. A source event is eligible only if it was visible in that snapshot and its recorded creation/decision/publication time is strictly before `feature_as_of`; windows are lower-inclusive, upper-exclusive. Snapshot the exact target revision selected by the job even when later content exists. The target revision must already exist by the cutoff. Never reconstruct an old profile location from today's profile.

For any reference product, choose the latest revision eligible at the cutoff by `(created_at, revision_no)` and count that product once. Its first publication must be known and before the cutoff; never infer a historical publication from its current availability. Current availability, account block status, raw report volume and AI scores are not price-reference exclusions or predictors: they do not supply a trustworthy historical safety label. Public browsing remains separately subject to current visibility and active-seller policy.

The present schema retains first publication time and immutable revisions but does not retain every intermediate publication/withdrawal event or profile edit. Runtime extraction freezes observed profile location; exports require an existing frozen snapshot when point-in-time reconstruction cannot be proven. Do not replace missing historical evidence with current values.

## Text and location normalization

1. Concatenate title, one ASCII space, and description.
2. Apply Unicode NFKC normalization, then Unicode `casefold()`.
3. Retain Unicode letters and numbers (`str.isalnum()`); replace every other character with one ASCII space.
4. Collapse whitespace to a single ASCII space and strip the ends.
5. The text fingerprint is lowercase SHA-256 hex of the resulting UTF-8 bytes.

Do not remove stop words, stem, transliterate, include seller identity, or include private text. Apply the same normalization to locations and suspicious phrases. Location equality compares the complete normalized value; missing/empty normalization produces a missing flag, not a mismatch.

The initial English phrase list is exactly: `wire transfer`, `western union`, `gift card`, `crypto only`, `deposit first`, `pay before viewing`, `no inspection`, `urgent payment`. Match complete contiguous normalized token sequences. Count each distinct phrase once even if repeated; overlapping different phrases may both match. The list is a contextual signal and deliberately includes phrases that may occur in legitimate warnings. Any dictionary change creates a new schema version.

Legacy `database/006_seed.sql` fingerprints use a simpler lowercase fixture expression and are not evidence that v1 normalization ran. Runtime duplicate extraction computes the v1 normalization from the eligible immutable title/description rather than trusting a legacy stored fingerprint. New application revisions store the v1 fingerprint. Preserve old immutable rows.

## Fixed predictor order and definitions

All predictors are numeric; booleans are integers 0/1. No identifier, provenance value, category ID or label is automatically appended to this vector.

| Order / name | Type | Exact definition |
| --- | --- | --- |
| 1. `price_ratio` | Nullable float | Target price / median reference price. Select other products first published in `[as_of - 90 days, as_of)`, same category, condition and currency as target, one latest eligible revision per product; exclude target and nonfinite/nonpositive prices. No other geographic/category fallback, no trimming/outlier deletion. Require at least 15 references; otherwise null. |
| 2. `comparable_count` | Nonnegative integer | Number of selected references, including when fewer than 15. |
| 3. `price_baseline_missing` | 0/1 | 1 exactly when fewer than 15 valid references exist; ratio is then null. |
| 4. `keyword_count` | Integer 0–8 | Count distinct matching phrases under the normalized-token policy above. |
| 5. `seller_age_days` | Nonnegative float | `(feature_as_of - seller.created_at).total_seconds() / 86400`. A registration after cutoff is invalid source data; do not invent zero. |
| 6. `prior_confirmed_fraud_count` | Nonnegative integer | Distinct other products of this seller with at least one revision whose latest canonical decision known before cutoff is evidence-backed `fraud`. Select the latest decision first; a later `unresolved`/`legitimate` on that revision replaces an earlier fraud verdict. Exclude target product and decisions at/after cutoff. Count each other product once, never reports or AI predictions. |
| 7. `posting_frequency_7d` | Nonnegative integer | Distinct seller products with first publication in `[as_of - 7 days, as_of)`. Include target only if its first publication precedes cutoff; edits and unpublished drafts never increment this count. |
| 8. `image_count` | Integer 0–6 | Number of immutable image associations attached to the job's exact target revision. |
| 9. `location_difference` | Nullable 0/1 | 1 iff both normalized locations are nonempty and differ; 0 if equal; null if either is missing. Seller location is the value observed in the extraction snapshot, retained in evidence. |
| 10. `location_missing` | 0/1 | 1 iff either normalized target or observed seller location is empty. |
| 11. `duplicate_text_count_30d` | Nonnegative integer | Other same-seller products first published in `[as_of - 30 days, as_of)` whose latest eligible revision has the same v1 normalized-text fingerprint. Exclude target product and its own revisions; count each product once. |

Use exact decimal prices to select the median and compute the division, then convert the finite ratio to float for the model. For even reference counts the median is the arithmetic mean of the two central prices. The 90-day selection horizon is a course-demo operational definition, not a claim that these are economically interchangeable goods.

## Snapshot and missing-value handling

Persist a JSON object with `schema_version`, ordered `features`, and `evidence`. Evidence includes cutoff, target identity, selected revision identity, raw observed seller/listing locations, reference product/revision identities and prices, reference count/median, window bounds, eligible prior-decision identities, selected publication/duplicate identities, and the normalization/dictionary version. Do not include private contact details, raw chats or attachment bytes. Evidence is access-controlled; public risk factors disclose only appropriate aggregate observations.

JSON missing predictors are `null`; never serialize NaN or Infinity. Validate ranges, predictor names/order, missing-flag consistency and finite values. An invalid required source (missing seller/target, future creation, wrong currency, corrupt associations) fails extraction and surfaces explicit pending/failed state. Missing baseline/location is valid uncertainty. It is never automatically a zero risk score.

Split related records before fitting preprocessing. A saved pipeline fits medians for `price_ratio` and `location_difference` on the training partition only, preserving the two explicit flags. If a column is entirely absent in training, use fixed fallback 1.0 for ratio and 0.0 for location; do not derive a fallback from validation/test. Keep other validated count/age predictors unchanged. Logistic Regression may additionally fit scaling on training only. Record fitted preprocessing and dependency versions with each artifact.

## Dataset/export and score contract

Identifiers, source/generator version, source license, synthetic flag, seller/template/duplicate group keys, feature time, schema version, label source and decision time are provenance columns, not predictors. Group connected seller/template/duplicate records into a single split before fitting anything. Final test records stay untouched during fitting/threshold choice. Report synthetic and real metrics separately when real rows exist; no real rows means real-data performance is not measured.

Reviewed labels come from the latest canonical decision at export cutoff, then require evidence-backed `fraud` or `legitimate`. A newer `unresolved` excludes an older label. Label time may be after feature time, but the label and subsequent evidence never alter that frozen feature vector. A feature time after label time is invalid. Synthetic records explicitly use generator labels, provenance and scenario families; they do not establish real fraud accuracy.

Fraud is the positive class (`fraud=1`, `legitimate=0`). Persist class mapping and extract the fraud probability by matching the fitted classifier's actual class labels. Integer risk score is `floor(100 * probability + 0.5)`, bounded to 0–100. Initial display thresholds are Low 0–39, Medium 40–74, High 75–100; the bound ruleset is authoritative. A score is an observed screening indicator, not a calibrated probability of actual fraud. Missing/stale/failed inference has no current numeric score.

## Version changes and verification

Changing predictors/order, normalization, phrases, windows, time-boundary rules, reference selection or imputation semantics requires a new immutable schema and compatible fitted model/ruleset. Threshold and maximum-age changes create a new ruleset; they do not retroactively rewrite historical assessments. SQL lease fencing and currentness checks continue to apply independently of feature validity.

Focused tests should cover exact window boundaries, target exclusion/inclusion, one reference per product, even-count medians, fewer-than-15 references, missing locations, repeated/embedded phrases, Unicode normalization, a later unresolved correction, future evidence exclusion, group leakage and frozen-snapshot retry. This checklist is required verification work, not a claim that tests have already run.
