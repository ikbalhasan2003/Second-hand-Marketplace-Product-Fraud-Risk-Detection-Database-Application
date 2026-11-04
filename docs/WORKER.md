# Risk worker and scheduler

The implemented worker uses PostgreSQL's existing `claim_risk_job`, `save_risk_snapshot`, `heartbeat_risk_job`, `fail_risk_job` and `complete_risk_job` functions. The process claims and commits quickly, extracts all source facts in one repeatable-read read-only transaction, persists the frozen snapshot in a separate claim-checked transaction, loads a trusted artifact and completes the result atomically through the database API. A background thread renews the lease every one-third of the configured interval, capped at thirty seconds, using a separate connection. No model runs inside a database trigger or a web request.

Snapshot keys are `schema_version`, `features`, `feature_evidence` and access-controlled `evidence`. The safe `feature_evidence` contains `latest_source_at` and `point_in_time_snapshot=true` for approved dataset exports. Full evidence retains the target, selected reference/review/publication/duplicate identities, exact median/price strings, observed locations, windows, cutoff and feature definition hash. It is never returned as public risk data. Runtime extraction observes the current profile within the same database snapshot; historical exports reuse this persisted snapshot and cannot reconstruct old profile locations from present values.

The fixed feature definitions are in [FEATURE_CONTRACT.md](FEATURE_CONTRACT.md) and shared `ml.contract` code. Price references use one latest eligible revision per other product, a 90-day first-publication horizon, exact category/condition/currency and at least fifteen prices. Seven-day posting counts use distinct first publications; thirty-day duplicates normalize immutable text rather than trusting legacy seed fingerprints. Seller fraud history selects the last decision before cutoff per revision before testing fraud eligibility, excludes the target and counts distinct products. All event windows are lower-inclusive and upper-exclusive. Missing baselines/locations remain null with explicit flags.

Use a separately provisioned worker login granted `secondhand_worker`; owner credentials are for controlled local verification only. Configure environment variables in the process environment or a private `.env`:

```powershell
$env:WORKER_DATABASE_URL = 'postgresql://worker-login@localhost/secondhand_fraud'
.\.venv\Scripts\python.exe manage.py run_risk_worker
.\.venv\Scripts\python.exe manage.py run_risk_worker --once
```

`--lease-seconds` defaults to 120 (permitted 1..600); `--poll-seconds` defaults to 2; `--max-jobs` bounds attempted jobs when provided. Heartbeats include the job's immutable claim token. A lost/replaced/expired lease cannot persist a snapshot or finish/fail a job. SQL recovers expired claims on the next claim and applies at most three attempts with bounded exponential retry delays. Persisted snapshots survive retry unchanged. Invalid features, incompatible dependencies, bad model checksums or unsafe paths produce a sanitized terminal `invalid_model_or_features` failure; other execution failures retry. Logs expose job identifiers and safe error codes, without raw source text or credential-bearing exception strings.

Completion of an old revision/context/model/ruleset is retained historically. The read-time `current_listing_risk` view decides currentness; such a result cannot become current after newer context or active configuration changes. Expired snapshots never supply a current score, and public Low-risk filtering must require `assessment_state='ready' AND risk_level='low'`. Missing, pending, scanning, failed and stale states are not converted to zero.

## Trusted registration and activation

First generate and train an actual artifact as described in [ML_PIPELINE.md](ML_PIPELINE.md). The operator importer intentionally accepts synthetic records only; real-review registration must retain canonical review links through the administrator export workflow.

```powershell
$env:REGISTRATION_DATABASE_URL = 'postgresql://migration-owner@localhost/secondhand_fraud'
.\.venv\Scripts\python.exe -m ml.training.register --dataset artifacts/datasets/synthetic-v1 --model artifacts/models/rf-synthetic-v1 --admin-id 1 --reason 'Register evaluated synthetic prototype'
```

Registration verifies the dataset/report/artifact checksums, schema, class mapping and exact installed inference dependencies. One transaction creates immutable schema/source metadata, a building dataset, split/record rows, validated frozen dataset with audit, registered Random Forest and measured evaluation slices, a draft ruleset (40/75 thresholds), and a typed registration audit. Existing versions are not overwritten. Activation remains an explicit audited administrator action using `activate_risk_configuration(model_id,ruleset_id)`; registration alone never changes active scoring. Artifact keys are relative to the trusted `ARTIFACT_ROOT`, and paths outside that root fail registration/loading.

## Scheduling and recovery

Use a separately provisioned login granted `secondhand_maintenance`:

```powershell
$env:MAINTENANCE_DATABASE_URL = 'postgresql://maintenance-login@localhost/secondhand_fraud'
.\.venv\Scripts\python.exe manage.py maintain_marketplace --daily --expire
.\.venv\Scripts\python.exe manage.py maintain_marketplace --expire
```

The command resumes existing activation/evidence/manual/daily campaigns in persisted bounded batches, at most 100 batches of 100 products by default. It never rebuilds a failed campaign from scratch; its saved cursor/receipts prevent duplicate context increments. Daily refresh uses the configured local timezone/date with a stable event key, and a repeated date is idempotent. `--date YYYY-MM-DD`, `--batch-size 1..1000` and `--max-batches` support controlled recovery. Expiry changes only old `placed` orders and is idempotent; accepted/shipped/disputed orders remain under participant or administrator control.

Windows Task Scheduler should run `maintain_marketplace --daily --expire` daily at 02:00 configured local time, and `maintain_marketplace --expire` every five minutes. Set the task's working directory to this repository, choose `.venv\Scripts\python.exe`, supply the management command as arguments, use a restricted service account/environment, and configure restart on failure. Keep the worker as a separately supervised long-running process. On Linux use separate systemd services/timers with the same command/credentials. Scheduling is operational setup; merely running these commands once does not install an OS schedule.

Back up database, immutable media, datasets, manifests and all referenced model bytes together. Restore into an isolated target before running web/worker/maintenance processes. The database does not preserve filesystem contents or prove that a public server, OS schedule or process supervisor has been deployed.
