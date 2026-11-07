# Second-hand marketplace and fraud risk screening

A PostgreSQL-backed Django application with a shared buyer/seller marketplace and protected administration, immutable listing revisions, private conversations/evidence, transactional orders, audited moderation and a leased Random Forest risk worker. Scores support human review; they never establish fraud or automatically block an account. Payments happen outside the application.

Use Python 3.13, Django 5.2 LTS and PostgreSQL 18. Exact Python packages are pinned in [requirements/lock.txt](requirements/lock.txt). See [Windows setup](docs/SETUP.md), [migration authority](docs/MIGRATIONS.md), [configuration](docs/CONFIGURATION.md) and [worker operation](docs/WORKER.md).

## Run locally on Windows

Create a new empty PostgreSQL database owned by your migration operator. Run from this repository in PowerShell:

```powershell
.\scripts\setup_windows.ps1
```

The first run creates `.venv`, installs dependencies and creates a private `.env` with a random session secret. Configure the database connection in `.env`, then rerun setup. Django migrations own installation; do not first install `database/install.sql` in the same database. Owner credentials are needed for migration and controlled provisioning. After setup, use separate web, worker, maintenance and training logins as described in the migration guide.

```powershell
.\scripts\setup_windows.ps1 -SeedDemo
.\scripts\start_demo.ps1
```

Open the [Marketplace](http://127.0.0.1:8000/) (shared sign-in at `/login/`, seller workspace at `/sell/`) or [Admin](http://127.0.0.1:8000/admin-app/). `seed_demo` provisions distinct synthetic accounts, three submitted listings, a purchase agreement once scanned, a two-person conversation and a pending report. All examples are explicitly synthetic. It leaves existing accounts, moderation decisions, orders and risk histories intact. Random login passwords are saved only in ignored `runtime/DEMO_CREDENTIALS.txt` and `runtime/demo_credentials.json`. Set `DEMO_PASSWORD` in the process environment before provisioning to choose a password; use `seed_demo --reset-passwords` only for an intentional rotation of the three demo identities.

Listing scans start pending until a compatible trained model is registered and explicitly activated. Generate/train/register a real artifact using [ML_PIPELINE.md](docs/ML_PIPELINE.md). Then `python manage.py seed_demo --activate-model` verifies and activates the registered `rf-synthetic-v1` version with an audit. Set `WORKER_DATABASE_URL`, then start the web and worker together:

```powershell
.\scripts\start_demo.ps1 -WithWorker
```

The startup script uses hidden background processes and writes logs/PID records under ignored `runtime/`. It refuses to take an occupied port. Run `scripts/stop_demo.ps1` to stop only processes whose PID, start time and executable still match its saved records. The scripts do not install OS scheduling or a production server. You may instead run `python manage.py runserver` and `python manage.py run_risk_worker` in separate terminals.

## Verify

```powershell
$env:DJANGO_DEBUG = 'true'
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

PostgreSQL integration tests require a trusted local test operator able to create disposable databases. Worker tests fit a real small synthetic artifact and verify inference, snapshots, fencing, recovery and stale-result exclusion. [Measured ML results](docs/evidence/ML_EVALUATION.json) describe synthetic scenarios only; real-world fraud accuracy is unmeasured. See [delivery verification](docs/DELIVERY.md), [the demonstration walkthrough](docs/DEMO.md) and [the academic report](docs/ACADEMIC_REPORT.md) for measured performance, restore evidence and remaining acceptance gaps.

Optional browser verification uses [requirements/browser-lock.txt](requirements/browser-lock.txt) and the installed Microsoft Edge executable. Playwright is not required by the running application, worker or training pipeline.

The 18 interface page groups share local Bootstrap assets, app navigation, bound forms, listing cards, risk states, purchase snapshots, order timelines and audit receipts. Order review pins the revision and assessment; uncertain submissions can be reconciled with their original request key. Chat renders history without JavaScript, then polls with ID deduplication and earlier-message loading. Risk and chat refreshes preserve loaded content, focus and scroll and back off after failures. Unsent listing, report and message text can be recovered within the same browser tab and identity; passwords and evidence files are not stored in browser drafts.

`tests/integration/test_interface.py` checks backend state rendering and, when optional browser dependencies are available, all 18 page groups at 1440px and 360px. Its Edge checks cover labels, horizontal overflow, dialog keyboard behavior, polling failure/recovery, draft preservation, message deduplication and upload feedback. Mobile inspection screenshots are written to ignored `.local/ui-qa/`.

Account registration, seller upgrades and reviewed sole-administrator provisioning: [Step 4 guide](docs/STEP_4_ACCOUNTS.md).

Seller listing submission, publication eligibility, messaging and fulfilment: [Step 5 guide](docs/STEP_5_SELLER_WORKFLOWS.md). Public listing pages, photos and checkout require a current successful scan. Start the configured risk worker; submission does not run inference in the request. After successful demo scans, rerun `seed_demo` to create its purchase agreement.

Buyer browsing, purchase assessment snapshots, reports, private evidence and profile editing: [Step 6 guide](docs/STEP_6_BUYER_WORKFLOWS.md).


Administrator visibility is available at `/admin-app/users/`, `/admin-app/products/` and `/admin-app/risk-logs/`. Private account inspection supports explicit reasoned blocking/unblocking; administrator membership remains controlled by provisioning. Report review maps stored `reviewing` to **Under Review**, preserving existing records. The dashboard separately counts new Pending reports.

`/admin-app/policy/` edits the unanswered-order timeout used by the order expiry maintenance process. Risk thresholds/assessment expiry remain versioned under `/admin-app/models/`. Every moderation change requires a reason and commits its audit in the same transaction. Apply marketplace migrations 0007 and 0008 with `.\.venv\Scripts\python.exe manage.py migrate` using the migration owner; apply `database/009_app_privileges.sql` after the base privilege script for fresh runtime-role setup. See [Step 7 verification](docs/PROJECT_UPDATE_VERIFICATION.md) for backup, migration and test evidence.


Step 8: blocked members can use `/account/appeals/`; active administrators review at `/admin-app/appeals/`. See [account appeal policy, migration and verification](docs/STEP_8_ACCOUNT_APPEALS.md).

AI settings, CSV exports and automatic training: see [Step 9 operations](docs/STEP_9_AI_TRAINING.md). Open `/admin-app/ai-settings/`; run `python manage.py run_training_worker` with a private trusted `REGISTRATION_DATABASE_URL`. Frozen datasets enqueue automatically; threshold changes only rescan. Candidates require explicit audited activation after evaluation.

## Completed project update

Start with [the operating guide](docs/OPERATIONS.md) for onboarding, sole-admin provisioning, moderation/appeals, scan-before-publication, CSV exports, durable training and explicit model activation. [Setup and upgrade commands](docs/SETUP.md) include both required privilege scripts. The [current requirements checklist](docs/PROJECT_UPDATE_PLAN.md) and [verification record](docs/PROJECT_UPDATE_VERIFICATION.md) distinguish implementation evidence from deployment prerequisites.

Run the trainer separately with privately configured `REGISTRATION_DATABASE_URL`, or use `.\scripts\start_demo.ps1 -WithWorker -WithTrainingWorker` for the local demo. Schedule maintenance as documented; startup scripts install no scheduler. Marketplace migrations through 0011 and accounts through 0003 are recorded as applied locally; Step 12 creates no migrations. Production runtime login/ownership separation, supervised services, TLS/proxy acceptance and real-world model evaluation remain required. Do not replay the original administrator credential file: its identity remains a seller after the approved separate-admin transition.
