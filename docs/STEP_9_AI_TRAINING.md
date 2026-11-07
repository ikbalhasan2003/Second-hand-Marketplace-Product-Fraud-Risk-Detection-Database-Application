# Step 9 - AI settings, CSV exports and durable training

Implemented 7 November 2026. Admin entry point: `/admin-app/ai-settings/`.

The existing ruleset editor validates Medium < High in 0-100 and assessment age in 1-168 hours. Saving creates a draft version and audit receipt. Explicit publication through Models and rules activates the compatible pair and queues the existing durable rescan campaigns. Ruleset drafts, thresholds and age changes do not fit a model. Their history and explanations remain in the existing models/ruleset/audit pages.

A newly frozen dataset is a training-input change. Migration 0010 adds an AFTER UPDATE trigger that atomically queues a training job in the same transaction as dataset freeze, including reviewed exports and trusted operator registrations. Existing frozen datasets can be selected in AI settings. A dataset row lock and unique dataset ID deduplicate concurrent requests. Dataset selection never mutates an already frozen dataset. New labels/review reversals continue to invalidate relevant risk context; incorporating them into model fitting requires freezing a new canonical reviewed dataset. Draft datasets and unrelated marketplace policy changes do not train. Feature/algorithm changes require a versioned compatible deployment and a new frozen dataset; arbitrary runtime feature/code edits are unsupported.

## Worker operations

Use the pinned `requirements/lock.txt` environment and configure `REGISTRATION_DATABASE_URL` privately for a trusted operator allowed to register model artifacts. The trainer deliberately does not borrow web or risk-worker credentials. Training reads the existing registered frozen manifest and JSONL artifacts under `ARTIFACT_ROOT`; it never substitutes newly generated synthetic data when real labels are missing. Synthetic operator datasets retain their explicit synthetic provenance.

```powershell
.\.venv\Scripts\python.exe manage.py run_training_worker
# Attempt one eligible job and exit:
.\.venv\Scripts\python.exe manage.py run_training_worker --once
# Managed local demo startup, with scan and training processes:
.\scripts\start_demo.ps1 -WithWorker -WithTrainingWorker
```

The existing stop script handles the recorded trainer process. Production should supervise/restart the command. A session advisory lock permits one trainer per database. Claims commit before fitting; another trainer cannot reclaim a live trainer's job. Process/connection death releases the lock, allowing the next trainer to recover interrupted running work. Failures remain visibly failed and become eligible after attempts * one minute. At most three attempts occur; after exhaustion, fix the cause and freeze a new dataset version. This intentionally avoids unlimited retries or resetting attempt history. No wall-clock timeout is imposed on a live fit; terminate a hung trainer through its supervisor to recover it.

The job stores the full immutable dataset registration, pipeline version, evaluation policy, requester and request audit ID. Each attempt retains exact dataset bytes, Python training sources, dependency versions, source hash, configuration snapshot, model metadata, fitted RF/LR artifacts and evaluation report in `ARTIFACT_ROOT/training/<job>/<attempt>/`. `checksums.json` covers retained inputs, sources and outputs; successful audit receipts link the snapshot and checksum-index digests. Existing trusted loading verifies schema/class order, artifact SHA-256 and exact installed dependency versions. Workers reject incompatible pipeline versions. Deploy web, scan worker and trainer with the same pinned environment; retain the snapshot source for reproducing an older attempt.

## Evaluation and activation

Fitting calls `ml.training.train.train`, preserving the existing connected grouped splits, train-only imputation/scaling, random forest/logistic regression comparison and baseline evaluation. Every train/validation/test partition needs at least 10 samples and both labels. Candidates must reach precision >= 0.50 and recall >= 0.50 on validation and test. These fixed minimum demonstration gates are stored in the queued configuration; they do not establish real-world effectiveness or tune against the test set.

Missing/corrupt datasets, insufficient independent labeled groups, absent dependencies, worker mismatch and failed evaluation produce failed jobs with actionable sanitized messages. Unexpected exception text, paths, connection strings and credentials are never persisted/displayed. Failed candidate artifacts remain available to the trusted operator but are not registered for activation. Retries preserve the same job/configuration and write a new attempt directory.

Passing candidates are registered against the existing dataset, including canonical review-backed datasets, with existing risk_models and model_evaluations history. Activation is always an explicit audited administrator operation. Training never retires or replaces the working model. Explicit activation uses the existing verified configuration API and queues its established reassessment campaigns. Admin status displays queued/running/succeeded/failed, attempt count, retry eligibility, request receipt, configuration and candidate link. Refresh the page to see updates.

## Export privacy and provenance

The existing administrator-only POST download now also offers CSV. Both formats verify registered dataset identity and checksum and commit the existing download audit receipt before delivery. CSV includes dataset version/checksum, cutoff, source type/attribution/access notes, label definition/source/decision time, partition, feature schema, synthetic flag and predictor columns. It excludes identities, contacts, chats, attachments and internal review/job IDs. Record keys remain pseudonymous research identifiers. The ZIP preserves the full validated machine-training contract, grouping and limitations.

CSV cells are quoted with Python's CSV writer. Strings beginning with spreadsheet formula prefixes (=, +, -, @), including leading whitespace/BOM variants, are prefixed with an apostrophe; leading tab/newline/carriage-return is neutralized. These presentation escapes can change numeric-looking CSV strings: use the verified JSONL ZIP for fitting. Downloads use private/no-store caching and attachment disposition. Unauthorized and blocked users retain the existing access denials. The web role can read status and invoke the admin-checked enqueue function but cannot alter job state or register model bytes. `database/009_app_privileges.sql` includes grants for hardening/redeployment after migrations.

## Migration and verification

Migration `marketplace.0010_ai_training` is additive and forward-only. Before applying it to the configured working database, created `.local/backups/step9-before-ai-training.dump` (553009 bytes). Migration applied successfully; counts remained 5 users, 3 listings, 1 order and 1 model. No historical dataset was silently retrained. Recovery requires restoring the database backup into a separate recovery database and reconciling later writes; back up private media and artifact storage separately.

Focused new training tests initially passed 11 cases; the combined training/admin/scan-worker/ML regression run passed 47 tests. Tests use real PostgreSQL and fitted artifacts, including a deliberately separable synthetic passing fixture with no performance claim. Coverage includes atomic freeze triggers, deduplication, successful fitting/registration, retained active model, explicit activation/rescans, evaluation failure, retries/exhaustion, interrupted recovery, concurrent worker exclusion, missing dependencies, corrupt data, threshold-only rescans, CSV escaping/projection and authorization. Final broader results are recorded below. No interactive browser layout review was performed. The background trainer must be launched with the configured trusted DSN; applying the migration alone does not start a service.

Final validation: full repository suite **134 passed in 134.80 seconds**. After adding actual undersized-data and restricted web-role job checks, the final training suite passed **13 tests in 4.30 seconds**. Django system checks, migration consistency, targeted Ruff and whitespace checks passed. The migration is applied; no persistent trainer was started and no working model was replaced. Configure the trusted registration DSN and start the worker command above to process future durable jobs.
