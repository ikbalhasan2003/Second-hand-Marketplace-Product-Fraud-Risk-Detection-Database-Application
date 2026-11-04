# Prompts 1–8 verification

Verified on 5 November 2026 (Asia/Shanghai). This checkpoint covers the configuration, Django foundation, PostgreSQL integration, accounts, Seller App, Buyer App, ML pipeline and risk worker requested by prompts 1–8 in `prompt.md`. No Admin App implementation was added or changed for this checkpoint. Existing Admin files and migrations were preserved; fresh installation necessarily applies the migrations already present in the repository.

## Executed checks

| Check | Actual result |
| --- | --- |
| Application, upload, ML and worker suite below | 38 passed in 10.97 seconds |
| Direct PostgreSQL integrity regression | 25 tests passed in 2.716 seconds |
| `database/008_privileges.sql` followed by `database/tests/check_privileges.sql` | Database privilege regression passed |
| Fresh Django installation in an empty isolated database | All existing migrations applied successfully |
| `manage.py makemigrations --check --dry-run` against that installation | No changes detected |
| `manage.py check` | No issues |
| Ruff over prompts 1–8 application modules and tests | All checks passed |

The focused application command was:

```powershell
$env:DJANGO_DEBUG = 'true'
$env:PGHOST = '127.0.0.1'
$env:PGPORT = '55432'
$env:PGUSER = 'postgres'
$env:PGDATABASE = 'pre9_verification'
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration/test_accounts.py tests/integration/test_schema.py tests/integration/test_seller.py tests/integration/test_buyer.py tests/integration/test_evidence.py tests/integration/test_worker.py -q
```

These are local test-operator settings, not deployment credentials. The local PostgreSQL 18.6 server listens on port 55432. The suite creates and destroys its isolated test databases; the named base database was not needed for pytest. Fresh migration verification used the separately created empty database `pre8_django_20261105`; direct SQL regression used `pre8_sql_20261105`. Both were retained for inspection. Never install reference SQL over a Django-owned database.

The new worker tests exercise a real heartbeat on a one-second lease, sanitized retry with a future retry time, rejection of completion by a released token, bounded daily-campaign progress, resumption by the maintenance command, and repeated daily execution without duplicate context increments or receipts. Existing tests cover stopped-worker reclamation, fencing, frozen snapshots, actual fitted inference, configuration invalidation and missing-artifact failure. The direct SQL suite also covers snapshot expiry, duplicate results, pending/failed states, campaign replay and unanswered-order expiry.

## Readiness and boundaries

No failing check or implementation blocker was found in the tested scope of prompts 1–8. Prompt 9 can be undertaken next. This checkpoint does not certify the Admin App or the final interface/delivery prompts.

Scheduling is implemented as management commands with the operational schedule documented in [WORKER.md](WORKER.md): daily refresh at 02:00 and campaign recovery/order expiry every five minutes. Windows Task Scheduler jobs and a persistent worker supervisor have not been installed. Their installation is deployment setup; the prompt 8 requirement for commands and documented scheduling is met. The tests do not prove that an unattended service is running.

Model training and worker verification use synthetic data and actual fitted artifacts. Real-world fraud effectiveness remains unmeasured. Final manual browser/accessibility checks, deployment, load acceptance and delivery work belong to later prompts and are not certified here.

Repository-wide Ruff found an existing unused `actor_transaction` import in `tests/integration/test_admin.py:14`. That prompt 9 file was deliberately left unchanged. Ruff passes for the prompts 1–8 scope.
