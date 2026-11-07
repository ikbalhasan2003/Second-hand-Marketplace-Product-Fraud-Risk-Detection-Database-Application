# Completed update: operating guide

Current as of 7 November 2026. Run PowerShell commands from the repository root. This guide describes implemented policy; [verification](PROJECT_UPDATE_VERIFICATION.md) distinguishes executed checks from deployment prerequisites.

## Entry points and onboarding

`/` is the shared public marketplace; `/login/` and `/register/` provide shared authentication. Seller work is under `/sell/`. `/admin-app/` is protected, with sign-in at `/admin-app/login/` and no public admin registration. Legacy buyer/seller GET links redirect safely; mutation requests must use current routes.

Buyer registration asks for email, password and confirmation and generates a display identity. Successful registration signs the member in. Seller registration (`/register/?role=seller`) additionally requires public seller name, city/service area and private contact email/phone. Existing buyers enable seller membership through Account and validated onboarding on the same identity. Profile/contact and password changes are under `/account/`; private contact is not public listing data. See [account details](STEP_4_ACCOUNTS.md).

## Sole administrator

Use the migration operator connection for controlled provisioning, never the web login:

```powershell
.\.venv\Scripts\python.exe manage.py provision_admin --inspect
.\.venv\Scripts\python.exe manage.py provision_admin admin@example.invalid --name "Marketplace Administrator"
```

The second command is an example new operator-selected identity and prompts privately for a validated password. Provisioning is locked, idempotent for the same active admin and audited; it never resets a password on startup. An existing marketplace identity cannot be promoted. Replacement requires exact reviewed former admin IDs and a reason; preserve records and verify recovery/access first. The local approved transition used a separate administrator identity because the original source-file email is an existing seller. Do not replay the original credentials file. [Step 4](STEP_4_ACCOUNTS.md) records the transition; no credentials are needed in this guide.

## Listings, risk and orders

Sellers retain private drafts, immutable submitted revisions and up to six validated JPEG/PNG/WebP images. Images are optional. Submission queues real asynchronous inference. Public discovery, listing photos/details and new checkout require a current successful assessment plus existing availability, visibility and account gates. Missing, pending, scanning, failed and stale are distinct states; none means zero risk. A ready result shows its actual score, band and recorded reasons. Currentness requires matching revision, context, active model/ruleset/schema and freshness. Old completions remain historical and cannot release a newer revision.

All completed Low/Medium/High bands may publish; High requires checkout acknowledgement. Scores advise human review and never automatically establish fraud, remove a listing or block an account. Model/dependency failures require operator repair; editing or configuration changes can make a prior result stale. Listing image requests always pass through `/listing-media/`; never serve either media directory directly as an unauthenticated static directory.

Buyer orders pin revision and assessment snapshots. Stored placed/accepted are pending phases; seller acceptance/shipping, buyer completion, cancellation and admin dispute resolution retain their guarded transitions. Withdrawal archives listings and preserves order/risk history. Payments and shipping verification are external. See [seller](STEP_5_SELLER_WORKFLOWS.md) and [buyer workflows](STEP_6_BUYER_WORKFLOWS.md).

## Moderation and appeals

Admin has user/product directories, account inspection, risk history and case/report review. Inspection is not impersonation. Report states display Pending, Under Review (`reviewing`), Resolved and Dismissed. Moderation requires a reason and transactionally committed audit identity, timestamp, target and changes. Account blocks, listing removal, report decisions and model activation are explicit actions. `/admin-app/policy/` controls unanswered-order expiry; versioned score bands/freshness live under `/admin-app/models/`.

Blocked members with authentication enabled can sign in, read retained history, fulfill permitted existing orders and use `/account/appeals/`, but cannot create trading activity, edit/upload listings, send chat or enable roles. Existing listing visibility is suppressed by account-status gates; history/orders are preserved. An authentication-disabled account cannot sign in. Appeals allow one open request, a reason and up to three private validated evidence images. `/admin-app/appeals/` supports review, approval/rejection and explicit audited unblock where appropriate; submission never unblocks. Owner/moderator evidence authorization applies. See [appeal policy](STEP_8_ACCOUNT_APPEALS.md).

## Exports, training and activation

Admin exports at `/admin-app/exports/` freeze canonical evidence-backed labels and point-in-time features. Newest unresolved corrections exclude older labels; unavailable historical features are not invented. CSV downloads include provenance, label/schema/synthetic definitions and predictors, exclude contacts/chat/evidence and neutralize spreadsheet formula prefixes. Use the validated JSONL ZIP for fitting because presentation escaping can alter CSV values.

Freezing a new dataset atomically queues a durable training job. Admin can request an existing frozen dataset in `/admin-app/ai-settings/`; dataset-based deduplication prevents repeated jobs. Draft thresholds do not train; explicit compatible ruleset activation triggers rescans. New labels enter fitting through a newly frozen dataset. Feature/algorithm changes require a compatible versioned deployment and dataset.

Trainer status is queued/running/succeeded/failed. One database advisory lock excludes concurrent trainers; interrupted work is recovered after connection death. Failures retry after attempts times one minute, at most three attempts; exhausted jobs require correcting inputs and freezing a new version. No live-fit wall-clock timeout is imposed. Artifacts, source/configuration snapshots and checksums are retained per attempt.

Train/validation/test each need at least 10 samples and both labels. Candidates must reach precision and recall of at least 0.50 on validation and test. Passing candidates register without replacing the active model; activation always requires an explicit audited administrator action and queues rescans. Synthetic-only evaluation demonstrates simulator behavior, not real-world fraud accuracy or calibrated probabilities. See [ML pipeline](ML_PIPELINE.md) and [training operations](STEP_9_AI_TRAINING.md).

## Required processes

Configure secrets privately in the environment or `.env`. Web uses PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD with a login inheriting `secondhand_web`. Scan uses `WORKER_DATABASE_URL` / `secondhand_worker`; maintenance uses `MAINTENANCE_DATABASE_URL` / `secondhand_maintenance`; trainer uses `REGISTRATION_DATABASE_URL` / `secondhand_training`. `TRAINING_DATABASE_URL` is the offline frozen-dataset exporter connection. Never substitute web/scan credentials for registration. All processes need compatible pinned dependencies and appropriate shared `ARTIFACT_ROOT`; retain private media and artifacts with database backups.

Run each long-running command in its own terminal or supervisor:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe manage.py run_risk_worker
.\.venv\Scripts\python.exe manage.py run_training_worker
```

Schedule maintenance (these commands alone do not install a schedule):

```powershell
# Daily at 02:00 marketplace local time; also resumes persisted rescan campaigns:
.\.venv\Scripts\python.exe manage.py maintain_marketplace --daily --expire
# Every five minutes:
.\.venv\Scripts\python.exe manage.py maintain_marketplace --expire
```

Use a production web server and supervisors in deployment. For managed local demonstration only:

```powershell
.\scripts\start_demo.ps1 -WithWorker -WithTrainingWorker
.\scripts\stop_demo.ps1
```

See [setup and upgrade](SETUP.md), [migration/recovery](MIGRATIONS.md), [scan worker](WORKER.md) and [demo](DEMO.md). Services, scheduler, production credentials/TLS and real-world evaluation remain operational prerequisites.
