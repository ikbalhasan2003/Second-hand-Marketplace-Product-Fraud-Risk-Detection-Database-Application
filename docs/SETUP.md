# Local setup (Windows PowerShell)

Use Python **3.13**, PostgreSQL **18**, and run from the repository root. The tested Python is 3.13.18; exact resolved packages (including transitive packages) are in `requirements/lock.txt`. Django 5.2 supports Python 3.13 ([official compatibility](https://docs.djangoproject.com/en/5.2/faq/install/)); Psycopg's [binary distribution](https://www.psycopg.org/psycopg3/docs/basic/install.html) includes its client library.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements/lock.txt
Copy-Item .env.example .env
```

Set a unique `DJANGO_SECRET_KEY` and PostgreSQL credentials in `.env`. Keep `DJANGO_DEBUG=true` local. Use HTTPS and `DJANGO_DEBUG=false` in deployment; secure session/CSRF cookies and redirects then apply. Never commit passwords, private media or trusted fitted pipelines.

Use a new empty PostgreSQL database. The Django migration path owns application installation; do **not** first run `database/install.sql` against the same database. Supply owner credentials for migration only, then switch `.env` to the web process login. See [migration authority](MIGRATIONS.md) for schema and privilege deployment.

```powershell
python manage.py migrate
python manage.py check
python manage.py collectstatic --noinput
python manage.py runserver
```

Enter at `/` for the shared marketplace, `/sell/` for seller work, and `/admin-app/` for administration. Shared sign-in is `/login/`; admin sign-in is `/admin-app/login/`. See [onboarding and operating policy](OPERATIONS.md). Administrator provisioning is trusted and sign-in only. Route `/listing-media/` through Django in production as well as development; neither listing nor private evidence storage may be exposed directly as public static media.

Logging goes to the console. It must not contain passwords, raw evidence, database credentials or session tokens. Database-backed sessions invalidate other sessions after a password change on their next authenticated request. Marketplace blocking and deactivation preserve existing order obligations; disabling `is_active` disables authentication entirely.

Run focused checks with:

```powershell
$env:DJANGO_DEBUG='true'
python manage.py check
python -m pytest
python -m ruff check .
```

Integration tests require PostgreSQL and permission to create a disposable test database. SQLite is deliberately unsupported. Do not run production with migration/owner credentials. Database regression scripts use their own **empty** disposable database, distinct from the application database.

## Prepared course demonstration

From the repository root, `scripts/setup_windows.ps1 -SeedDemo` installs the pinned environment, applies Django-owned migrations and provisions separate synthetic Buyer/Seller/Admin accounts. Configure its generated private `.env` first if database access is not already configured. Credentials are written only to ignored `runtime/DEMO_CREDENTIALS.txt`; do not copy them into a report or commit them.

Run `scripts/start_demo.ps1` for the web application, or `scripts/start_demo.ps1 -WithWorker` after configuring the separate worker database login and registering/activating the trusted model. Without an active compatible model, pending assessments are expected. Use `scripts/stop_demo.ps1` to stop only the saved matching demo processes. These scripts start local background processes, not production services or an OS scheduler. Follow [DEMO.md](DEMO.md) for the cross-role walkthrough and [DELIVERY.md](DELIVERY.md) for measured acceptance evidence.

Optional browser checks require `python -m pip install -r requirements/browser-lock.txt` and installed Microsoft Edge. They render Django responses with local assets at 1440px and 360px, exercise keyboard/dialog/polling/upload behavior, and write mobile screenshots under ignored `.local/ui-qa/`. An absent optional dependency skips this browser check; a skipped check must not be reported as executed.

## Exact fresh-install and upgrade sequence

For a fresh installation create an empty database first; for an upgrade preserve the existing database. Configure the controlled migration/role-management connection privately using PG variables. `psql` uses those same libpq variables; put its binary on PATH. Before upgrading, stop web/scan/training and scheduled writes and retain a recoverable coordinated database/media/artifact backup. Use a unique backup filename; verify restoration into a separate database before continuing.

```powershell
pg_dump --format=custom --file=runtime/before-update.dump
createdb secondhand_upgrade_restore
pg_restore --exit-on-error --dbname=secondhand_upgrade_restore runtime/before-update.dump
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --noinput
psql -X --set=ON_ERROR_STOP=1 --file=database/008_privileges.sql
psql -X --set=ON_ERROR_STOP=1 --file=database/009_app_privileges.sql
.\.venv\Scripts\python.exe manage.py migrate --check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Create `runtime` first if absent (`New-Item -ItemType Directory -Force runtime`). Backup/restore commands apply to upgrades; fresh installs have no preceding application data to recover. Review backup contents/ledger and retain subsequent writes for reconciliation; never restore over the working database automatically. See [the tested migration drill and recovery](STEP_10_DATABASE_DEPLOYMENT.md). Provision separate runtime LOGIN roles inheriting the documented process groups, switch away from owner credentials, and start/schedule the processes in [OPERATIONS.md](OPERATIONS.md). `setup_windows.ps1` does not apply the two privilege scripts or provision production login roles.
