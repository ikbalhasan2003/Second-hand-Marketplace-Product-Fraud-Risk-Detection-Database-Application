# Project update verification

## Step 12 - Documentation completion (2026-11-07)

Updated README, setup/upgrade, configuration, accounts, buyer/seller, migration,
scan worker, ML and demo guides. Added [current operations](OPERATIONS.md),
updated the Step 1 requirements checklist with implementation/test mapping and
open operational acceptance items, and marked original PRD/architecture design
contracts as historical. No credentials were added. Existing application and
workspace edits were preserved; no commit, push or deployment was performed.

Executed in the project venv from the repository root:

| Command / inspection | Actual result |
| --- | --- |
| `.\.venv\Scripts\python.exe manage.py check` | No issues (0 silenced). |
| `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` | No changes detected. |
| `.\.venv\Scripts\python.exe manage.py migrate --check` | Exit 0; no pending migrations. |
| `.\.venv\Scripts\python.exe manage.py showmigrations accounts marketplace` | Accounts 0001-0003 and marketplace 0001-0011 all marked applied. |
| `git diff --check` | Passed. |
| Local Markdown link and command-file checks | All relative links in the 10 principal updated guides resolved; documented custom management command files exist. Final broader check: 103 relative links across 15 updated files resolved; final `git diff --check` passed. |

Step 12 is documentation-only: no migration was created or applied, no seed,
backup/restore, fitting, service startup or database mutation was performed.
Setup/upgrade examples were checked against scripts/commands, not executed over
the working database. No application test suite was rerun for these prose changes.
Step 11 results below remain the actual prior test evidence: initial full suite
138 passed; expanded run 138 passed/1 failed, then affected interface module
14 passed after fixes; independent reference database suite 25 passed. Do not
combine those into a claimed new full-suite pass.

Update migrations delivered in earlier steps: accounts
0002_administratortransition/0003_onboarding_guards and marketplace
0005_scan_publication through 0011_deployment_integrity. The ledger check above
confirms applied state; individual apply/backup evidence belongs to the owning
step. Step 10 applied only 0011 plus privilege scripts 008 and 009.

Required startup: web, `run_risk_worker`, `run_training_worker`, and externally
scheduled `maintain_marketplace --daily --expire` (daily) /
`maintain_marketplace --expire` (five minutes). [SETUP.md](SETUP.md) and
[OPERATIONS.md](OPERATIONS.md) give exact commands and private process-role
configuration. Remaining deployment prerequisites: replace local superuser runtime
credentials/ownership, configure compatible trusted artifacts and supervised
processes/schedules, verify production TLS/proxy behavior and complete broader
accessibility/human rehearsal. Real-world accuracy remains unmeasured; synthetic
results and candidate gates are not real-world validation. No known documentation
implementation blocker remains within the verified scope.


## Step 11 - Security, workflows and responsive verification (2026-11-07)

Verification used the existing project virtual environment, disposable PostgreSQL
application test databases and synthetic records/artifacts. Existing workspace
changes from Steps 1-10 were preserved. No working user data was seeded, edited
or deleted; no working migration or privilege script was applied in this step.

### Commands and results

Commands were run from `D:\SecondHandFraudDB` in PowerShell:

| Actual command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe manage.py check` | Passed: no issues (0 silenced). |
| `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` | Passed: no changes detected. |
| `.\.venv\Scripts\python.exe manage.py migrate --check` | Passed: exit 0, no pending migrations. |
| `.\.venv\Scripts\python.exe -m ruff check .` | Passed, including pre-existing local changes. |
| `.\.venv\Scripts\python.exe -m pytest -q -ra` (initial baseline) | 138 passed in 137.84s; optional Edge browser check ran. |
| `.\.venv\Scripts\python.exe -m pytest -q -ra` (expanded coverage) | 138 passed, 1 failed in 107.81s: new browser coverage found duplicate appeal page headings. Fixed both appeal templates; focused rerun recorded below. |
| `.\.venv\Scripts\python.exe scripts/verify_migrations.py --pg-bin .local/pg-server/pgsql/bin` | Passed; fresh/upgrade catalogs identical, grants allow/deny and two-connection appeal race passed. |
| `.\.venv\Scripts\python.exe -m pytest tests/integration/test_interface.py -q -ra` (after heading fixes, sequential) | 14 passed in 137.86s; no skips, including the expanded Edge check. |
| `.\.venv\Scripts\python.exe -m pytest database/tests/test_database.py -q -ra` (child process with private disposable DSN) | 25 passed in 1.38s. |

Migration verification evidence: `runtime/migration-checks/2ee04e3c075d/report.json`
and `commands.log`. The script created separate fresh/upgrade databases and did
not use `--apply-working`. The configured working target was local
`secondhand_fraud`, port 5432; no new migration was required.

The reference SQL suite was launched through a PowerShell Python here-string:
Django settings were loaded, an explicitly named random
`step11_reference_<uuid>` database was created using psycopg SQL identifiers,
connection fields were passed through `make_conninfo` to the child environment's
`DATABASE_TEST_DSN`, and `subprocess.run([sys.executable, '-m', 'pytest',
'database/tests/test_database.py', '-q', '-ra'], env=env)` ran. No DSN or password
was printed. Successful reference database: `step11_reference_e125a60c6ee4`.
This suite installs only the standalone reference schema into its own empty
DB; it does not install that schema over the Django application.

### Coverage and changes

- `test_accounts.py` / `test_routes.py`: anonymous and role gates, login/logout,
  safe deep-link redirects, onboarding/role upgrades, duplicate identity,
  password hashing and controlled sole-admin provisioning.
- `test_seller.py` / `test_uploads.py`: ownership, private drafts/images, bounded
  uploads, immutable revisions, publication/scan gates, unavailable models,
  failed/stale scans, late old completions, and seller order obligations.
- `test_buyer.py` / `test_evidence.py`: filters, reports/evidence, private chat,
  participant authorization, blocked sessions, duplicate purchase requests and
  transactional orders. Database/reference tests exercise competing purchases.
- `test_admin.py`: moderation transitions, audit details and rollback, privacy,
  risk filters and policy, restricted web-role execution. Expanded direct POST
  rejection coverage for buyer, seller and blocked-admin sessions to AI settings,
  appeals, policy and account moderation. Added CSRF enforcement for these forms
  even with an authenticated administrator.
- `test_appeals.py`: blocked login and appeal access, evidence privacy, duplicate
  appeals, decisions, transactional unblock/audit rollback, restricted web role,
  self-approval denial and terminal-history protection.
- `test_training.py` / `test_worker.py` / `test_ml.py`: rule-only rescans,
  CSV authorization/provenance/formula protection, real fitted synthetic training,
  restricted training privileges, durable request immutability, failure sanitizing,
  retry exhaustion, worker locking/recovery, insufficient data/dependencies,
  tampered data, evaluation gates and explicit activation retaining the old model.
- `test_interface.py`: extended real rendered-page browser checks to the shared
  homepage and login pages, new admin directories/account detail, risk history,
  policy, AI settings, appeal review, and blocked-user appeals. Every captured
  route must return 200 before browser inspection. Fixed crowded admin navigation
  using wrapping, spaced links inside its labelled navigation region. Removed
  duplicate h1 headings from both appeal pages; the shared base already supplies
  the page heading.

### Browser inspection and boundaries

Installed Microsoft Edge runs headlessly through Playwright at 1440x900 and
360x900. Documents come from Django test-client requests against the isolated DB;
local CSS/JS are served to Edge through intercepted requests. This is browser
layout/interaction verification, not a production-server end-to-end test.
Assertions inspect headings, associated labels, horizontal page overflow,
keyboard dialog Enter/Escape/focus restoration, focused validation errors,
chat refresh errors/recovery, preserved draft/focus/scroll, deduplication,
earlier-message loading, risk refresh failures and upload validation feedback.
Empty admin queues/exports/appeals and queued training status use persisted
synthetic state; no success status is fabricated.
Pending/scanning/failed/stale assessment labels and suppression of old scores
are separately exercised in rendered-template and workflow tests.

Screenshots are in ignored `.local/ui-qa/` (buyer, account, admin model settings,
AI settings and blocked-user appeals, at mobile and desktop widths). Screenshots
are local synthetic evidence, not committed user evidence. Visually inspected
buyer mobile, account desktop, admin models mobile and AI settings desktop/mobile,
plus blocked-user appeals mobile. The revised navigation wraps without joined
links; appeal pages have a single title and readable labelled fields. Dense
training-table cells still wrap at 360px; no page-wide horizontal overflow was
detected. This is functional responsive coverage, not a full visual redesign.

### Failed attempts and acceptance gaps

A targeted `python -m pytest tests/integration/test_interface.py -q -ra` was
accidentally launched while the baseline full suite owned the same default test
DB: 8 passed, 6 setup errors (`DuplicateDatabase`, then fixture setup errors).
It is an orchestration collision, not an application pass. The initial reference
suite harness also failed before running tests because Django connection options
included psycopg's `context`, which is invalid in a DSN; the corrected harness
used only explicit connection fields. An unused empty disposable database from
that first harness may remain. Fresh/upgrade and reference DBs are retained for
inspection. No working database records were used for these tests.

The configured local operator is a superuser. Restricted `SET ROLE` tests and
fresh-install allow/deny tests passed; separate production login credentials,
non-login ownership and deployment configuration remain operational prerequisites.
This step does not claim production TLS/cookie behavior, reverse-proxy behavior,
full assistive-technology/contrast certification, every viewport/browser, real
external worker processes, or real-world fraud accuracy. Candidate evaluation
uses synthetic data. No live production or working-data browser interactions
were performed. No unrelated baseline test/lint failures were observed. After fixing the newly
detected heading defect, the entire affected interface module passed. The full
139-test suite was not rerun a third time: its other 138 tests passed in the
expanded run, and the focused rerun verified the changed templates and browser
behavior. No failed check is described as a successful full-suite run.


## Step 10 - Database reconciliation (2026-11-07)

Completed schema review and added `marketplace.0011_deployment_integrity` for
appeal/training indexes, retained training provenance and private trigger-helper
permissions. Consolidated extension grants into one transaction and added scoped
training-process privileges. See [deployment evidence and recovery](STEP_10_DATABASE_DEPLOYMENT.md).

Executed `.venv\Scripts\python.exe scripts/verify_migrations.py --pg-bin
.local/pg-server/pgsql/bin --apply-working`: disposable fresh installation,
populated upgrade through marketplace 0010 to 0011, privilege allow/deny checks,
independent-connection open-appeal race, custom backup, verified disposable restore,
working migration and privilege scripts all passed. Subsequent verification also
compared fresh/upgrade columns/defaults, constraints, indexes, functions and triggers:
identical. Private reports are in `runtime/migration-checks/0d19ce5352ad/` and
`runtime/migration-checks/7659495ce63c/`.

Working target: local `secondhand_fraud` on port 5432. Only
`marketplace.0011_deployment_integrity` ran; previous migrations were already
applied. Applied `database/008_privileges.sql` then `database/009_app_privileges.sql`.
No pending Django migrations remain. Reference bootstrap/seed and optional
pgvector SQL were not applied to the working database.

Final regression command using the project venv:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_schema.py tests/integration/test_accounts.py tests/integration/test_appeals.py tests/integration/test_training.py tests/integration/test_worker.py tests/integration/test_buyer.py tests/integration/test_seller.py tests/integration/test_admin.py -q
```

**100 passed in 41.55 seconds**, including fitted training under the restricted
training role and immutable training request checks. Django `check`,
`makemigrations --check --dry-run`, `migrate --check`, and Ruff on the Step 10
Python changes all passed. No browser review was performed in this database step.
The working local connection remains a superuser; separate production runtime
logins and non-login ownership remain deployment prerequisites. No production
credential/ownership conversion or optional extension execution is claimed.

## Step 7 ? Administrator moderation and visibility (2026-11-07)

Implemented account/listing directories, account inspection with selected private contact fields, account blocking/unblocking, historical risk evidence with level/category/capture-date filters, distinct pending-report count, and audited unanswered-order-timeout policy editing. Existing listing removal/restoration, dispute review, immutable revision decisions, report assignment and model/rule activation remain in use.

Report mapping is explicit and requires no data rewrite: pending ? Pending; reviewing ? Under Review; resolved ? Resolved; dismissed ? Dismissed. Pending can advance to Under Review or either terminal state; Under Review can advance to either terminal state. Closed reports remain immutable and accessible in their listing revision cases. Outcome text and resolution time are now included in report audit changes.

Directories show recorded orders and their buyer identities, including cancelled order history with its status. Listings without orders have no assigned buyer. Account inspection selects identity, contact, status and join date; it never selects password hashes, sessions, permissions or authentication tokens. Recent account listings/purchases are capped at 25 and labelled accordingly.

Risk filters use the assessed immutable revision category and feature capture time, with inclusive calendar end dates in the configured marketplace timezone. Only stored snapshots, observed factors and optional model explanations are shown. Missing evidence is labelled rather than inferred. Risk bands remain advisory.

Policy editing supports only the unanswered-order timeout (1?8760 hours), used by existing order expiry behavior. Risk score thresholds and assessment age retain the existing versioned ruleset/activation controls. No admin membership or impersonation controls were added. Policy audit insertion runs through a restricted trigger with a fixed search path; the web role receives only timeout-column UPDATE access. Stale writes and audit failures roll back.

### Database

Verified configured target `secondhand_fraud` and migration history through marketplace 0006. Created recoverable custom-format PostgreSQL backup `.local/backups/step7-before-admin-visibility.dump` (537878 bytes) before applying changes. Applied `marketplace.0007_admin_visibility` and `marketplace.0008_policy_audit_privileges`. The former extends report audit fields and singleton-policy target receipts; the latter grants trigger-only audit privileges without granting audit INSERT to the web process. No account, listing or report data backfill/deletion. Migrations are intentionally forward-only: restore the pre-change backup into a recovery database to recover the preceding schema/data, accounting for subsequent writes before any replacement.

### Validation

Use `.\.venv\Scripts\python.exe`; the system Python lacks Django/pytest. Django `check` passed; `makemigrations --check --dry-run` reported no changes. Targeted Ruff checks passed. The initial expanded admin/buyer/account regression run passed 58 tests. Restricted-role policy testing then exposed missing trigger audit privileges; migration 0008 corrects this, with the final rerun recorded below.

Tests run against disposable PostgreSQL test databases with synthetic users/listings and actual fitted synthetic model inference. Coverage includes role denial/private caching, user/product search, unsold buyer absence, actual order buyer identity, report transitions, audit details and rollback, account state changes, policy validation/stale writes/web-role execution, risk category/level/date filters, and the existing buyer/account workflows. No interactive browser or mobile layout review was performed in this step.

Final validation: `python -m pytest tests/integration/test_admin.py tests/integration/test_buyer.py tests/integration/test_accounts.py -q --disable-warnings --maxfail=1` using the project venv: **59 passed in 29.12s**. Final Django system check, migration consistency check and targeted Ruff check all passed. Both Step 7 migrations applied successfully to the working database.
