# Reproducible dataset and model workflow

The implemented offline pipeline uses `marketplace-v1` from [FEATURE_CONTRACT.md](FEATURE_CONTRACT.md). Its canonical machine-readable definition and SHA-256 are exposed by `ml.contract`. Predictors contain eleven numeric values, including explicit price/location missing flags. Identifiers, source metadata, labels, categories and timestamps never enter the predictor matrix.

Run commands from the repository root after installing the pinned requirements. Outputs are private runtime files under ignored `artifacts/`; use new version directories because datasets and fitted versions refuse overwrite.

```powershell
.\.venv\Scripts\python.exe -m ml.datasets.generate --output artifacts/datasets/synthetic-v1 --count 5000 --seed 20261104
.\.venv\Scripts\python.exe -m ml.training.train --dataset artifacts/datasets/synthetic-v1 --output artifacts/models/rf-synthetic-v1 --model-version rf-synthetic-v1
```

Generation defaults to 5,000 synthetic records over five categories. A seeded latent scenario determines the simulated label; overlapping noisy signals and independent perturbations prevent a label from being one feature threshold. The simulated aggregate features are timestamped point-in-time summaries. They are not recorded activity of real sellers. Template families connect two seller groups; seller/template/duplicate connected components are allocated to approximately 70/15/15 partitions before fitting. The seeded component assignment is deterministic. No independently authored challenge set currently exists; the pipeline supports a separate `challenge` partition and rejects overlaps with development records.

`records.jsonl` and `manifest.json` preserve source/license notes, generator version, seed, feature definition/hash, feature times, label source/time, synthetic flag, pseudonymous grouping keys, exact split manifest and dataset checksum. All evidence times must be strictly before feature time; label decisions must be at or after feature time and no later than export cutoff. Related seller/template/duplicate records cannot cross partitions. Unknown predictor fields, nonfinite values, inconsistent missing flags, corrupt checksums and private extra record columns fail validation. New generator versions or label corrections require new output directories.

The fitted artifact contains preprocessing plus `RandomForestClassifier`. Price/location medians are fit on training rows only; all-null columns use fixed ratio=1/location=0 fallbacks. Logistic Regression adds training-only scaling. Both models use class balancing based on training labels and fixed random seeds. The transparent rules baseline is defined in the evaluation report. All three methods use identical frozen partitions and a fixed 0.5 classification threshold. There is no hyperparameter or threshold search against the final test. The evaluation report includes fraud precision, recall, F1, average precision, authoritative confusion counts, class prevalence, false-positive record keys, and source/category slices with sample counts. A slice without positive labels has null average precision. Synthetic-only measurements demonstrate this simulator, not real-world effectiveness or probability calibration.

`model.json` records artifact SHA-256, dataset checksum/version, feature schema/hash/order, class mapping, seed, actual installed Python/scikit-learn/NumPy/SciPy/joblib versions, Git revision, fitted imputation statistics, evaluation checksum and limitations. `pipeline.joblib` and `logistic_regression.joblib` are real fitted artifacts. Training never changes live marketplace data or activates a version.

Trusted registration must verify the artifact against this metadata, register an immutable new model/dataset/schema version and leave activation to an audited administrator action. `ml.training.artifacts.load_trusted_pipeline` accepts the trusted storage root and immutable registration values; it resolves paths under that root, verifies exact training/inference dependencies, checksum, schema, classifier classes and predictor width before use. The checksum alone does not make unknown joblib content safe. Only operator-produced project artifacts may be registered because unpickling can execute code. Uploaded or externally obtained models must not enter this trust boundary.

## Approved real-data export

The exporter consumes an already frozen, administrator-approved `dataset_versions` record using the restricted training database role. It reads dataset/provenance/schema tables only; it does not query contacts, chats or attachments. Every `dataset_records.feature_values` JSON must have exactly:

```json
{
  "features": {"price_ratio": null, "comparable_count": 0, "price_baseline_missing": 1, "keyword_count": 0, "seller_age_days": 12, "prior_confirmed_fraud_count": 0, "posting_frequency_7d": 1, "image_count": 1, "location_difference": null, "location_missing": 1, "duplicate_text_count_30d": 0},
  "feature_evidence": {"latest_source_at": "2026-01-01T00:00:00+00:00", "point_in_time_snapshot": true},
  "category": "furniture"
}
```

The safe chronology metadata is derived from a genuine frozen worker snapshot; it must not be invented. The feature schema definition must contain `schema_sha256` matching `ml.contract.SCHEMA_SHA256`. Canonical review selection and privacy-safe pseudonymization happen in the audited administrator registration workflow before freezing: select the newest decision at export cutoff, then require evidence-backed `fraud` or `legitimate`; newer `unresolved` excludes older labels. Existing historical data without a provable point-in-time feature snapshot is ineligible. Today's mutable seller profile must not replace missing historical facts.

```powershell
$env:TRAINING_DATABASE_URL = 'postgresql://training-login@localhost/secondhand_fraud'
.\.venv\Scripts\python.exe -m ml.datasets.export --dataset-version reviewed-v1 --output artifacts/datasets/reviewed-v1
```

Focused verification:

```powershell
$env:DJANGO_DEBUG = 'true'
.\.venv\Scripts\python.exe -m pytest tests/unit/test_ml.py -q
```

Executed on 4 November 2026 with Python 3.13 and the pinned dependencies: all six focused tests passed. The actual 5,000-record run produced dataset SHA-256 `7038f56947f8a07f9dc9e501aff19851cf40190a2c286f648fe9c5c9735fc959` and trained Random Forest artifact SHA-256 `727e9b7c6346295ae8e9bdfb87fe35aba395935691d6394a0647aa3221aef2bb`. Complete measured slices and confusion matrices are retained in [ML_EVALUATION.json](evidence/ML_EVALUATION.json), with actual registration metadata in [ML_MODEL_METADATA.json](evidence/ML_MODEL_METADATA.json). The test partition contains 760 synthetic records (185 fraud scenarios); real-data performance remains unmeasured.

| Method | Precision | Recall | F1 | Average precision |
| --- | ---: | ---: | ---: | ---: |
| Rules | 0.605442 | 0.481081 | 0.536145 | 0.514906 |
| Logistic Regression | 0.560150 | 0.805405 | 0.660754 | 0.606811 |
| Random Forest | 0.588235 | 0.756757 | 0.661939 | 0.555881 |

These are synthetic-only held-out measurements. Random Forest remains the required initial algorithm; this run does not establish it as the best classifier.

`ml.training.register` is a trusted owner-only CLI that verifies this output and records the schema/source/dataset/splits/records, freezes the dataset with the existing audit trigger, registers the model and its measured evaluation rows, and creates an unactivated draft ruleset. It also writes a typed registration audit in the same transaction. Existing immutable versions reject replacement. The importer intentionally accepts only synthetic rows; review-backed registration must preserve the canonical database review/product/revision linkage through the administrator workflow.

```powershell
$env:REGISTRATION_DATABASE_URL = 'postgresql://migration-owner@localhost/secondhand_fraud'
.\.venv\Scripts\python.exe -m ml.training.register --dataset artifacts/datasets/synthetic-v1 --model artifacts/models/rf-synthetic-v1 --admin-id 1 --reason 'Register evaluated synthetic-only prototype'
```

The local PostgreSQL registration was actually executed and returned dataset/model/ruleset IDs 1/1/1. It created a frozen dataset and measured model evaluations without activating inference. The local synthetic operator identity has an unusable password.

Measured execution results and remaining application/database integration gaps belong in the delivery verification record; this document does not assert unexecuted checks or real-data performance.

## Completed update operations

See [OPERATIONS.md](OPERATIONS.md) for current publication gates, separate scan/training/maintenance startup, export provenance, durable training triggers and explicit activation policy. See [SETUP.md](SETUP.md) for exact fresh-install/upgrade commands and [PROJECT_UPDATE_VERIFICATION.md](PROJECT_UPDATE_VERIFICATION.md) for measured evidence and operational limitations.
