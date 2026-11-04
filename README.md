# Second-hand marketplace and fraud risk screening

A PostgreSQL-backed Django application with separate Buyer, Seller and Admin interfaces, immutable listing revisions, private conversations/evidence, transactional orders, audited moderation and a leased Random Forest risk worker. Scores support human review; they never establish fraud or automatically block an account. Payments happen outside the application.

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

Open [Buyer](http://127.0.0.1:8000/buyer-app/), [Seller](http://127.0.0.1:8000/seller-app/) or [Admin](http://127.0.0.1:8000/admin-app/). `seed_demo` provisions distinct synthetic accounts, three published listings, a purchase agreement, a two-person conversation and a pending report. All examples are explicitly synthetic. It leaves existing accounts, moderation decisions, orders and risk histories intact. Random login passwords are saved only in ignored `runtime/DEMO_CREDENTIALS.txt` and `runtime/demo_credentials.json`. Set `DEMO_PASSWORD` in the process environment before provisioning to choose a password; use `seed_demo --reset-passwords` only for an intentional rotation of the three demo identities.

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
