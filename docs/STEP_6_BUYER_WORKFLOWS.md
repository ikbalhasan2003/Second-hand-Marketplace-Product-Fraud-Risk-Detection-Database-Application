# Step 6 buyer workflows - 7 November 2026

Public browsing at `/` and `/listings/` supports category, inclusive price bounds, exact case-insensitive location, condition, full-text search, risk and price sorting. Invalid selections return bound field errors and no results. Prices accept at most 12 digits with two decimal places. Pagination retains filter query parameters; category navigation changes only category and resets the page. GET URLs retain selections across refresh/back navigation and can be bookmarked. Clear filters explicitly resets the search.

Publication continues to require a current completed scan. Pending, scanning, failed and stale listings are withheld from anonymous browsing, photos and checkout. Authorized owners and buyers with the matching purchased/reported revision can inspect retained content and honest risk states. Completed assessments show the real score, warning factors and configuration; historical revisions never borrow today's assessment. Risk indicates concerns, not proof of fraud.

Authenticated active buyers can start an idempotent seller conversation, purchase an available listing, and inspect their own orders. Starting a conversation also rejects inactive/blocked sellers. The existing participant checks protect sends, polling, receipts, orders and reports. Blocked users retain historical reading and existing order obligations under the existing policy. Private evidence is accessible only to the reporter and an active administrator; the reported seller cannot read it. Decoded JPEG/PNG/WebP evidence is limited to three images per case, with bounded upload size, metadata removal and transaction/file cleanup on failure. Open reports permit additional evidence; closed cases reject it.

Purchasing retains the SQL locks, unique sale constraint, request-key reconciliation, immutable revision and assessment-review token checks. A new database trigger captures the actual ready assessment at insertion, including risk ID, revision, score, level, timestamps, model/ruleset IDs and recorded warning reasons. The snapshot is immutable and displayed in participant order details. Existing orders have NULL snapshots: no historical assessment is guessed or backfilled.

`/account/` now provides a separate profile form for display name, city/area and private support contact. Contact must be a valid email or phone; seller memberships still require location/contact. Only the signed-in user's whitelisted profile columns are updated. Submitted identity, email, status and privilege fields cannot change those records. Password changes retain current-password validation and session invalidation. Public pages never render private contact. Changing a seller location increments listing contexts and queues reassessment through existing triggers, including when onboarding is repeated; name/contact-only changes do not retrain the model. Authenticated responses receive `Cache-Control: private, no-store`.

## Migration and recovery

Created `marketplace.0006_order_assessment_snapshot` and `sql/008_order_assessment_snapshot.sql`, with synchronized unmanaged Order model/migration state. This adds a nullable JSON snapshot and database capture/immutability guards, without replacing existing revisions, assessment history or orders. Existing table-level process grants cover the added column; capture uses the existing definer-owned scan guard and no new callable privileged interface is exposed. No old migration was edited.

Verified working target: `secondhand_fraud`, PostgreSQL port 5432. A custom backup is retained in ignored `runtime/backups/step6_before_20261107.dump`. Restored it into a unique disposable database and applied the SQL upgrade successfully; counts remained 5 users, 3 listings, 1 order and 7 risk results. The migration then applied successfully to the configured working database. No working user data was generated for verification.

Migration reversal is intentionally unsupported to protect historical snapshots. Recovery requires a coordinated application/database restore using the backup and matching media backup. Prefer forward repair for an incident after new orders exist; restoring an old backup would lose intervening writes. Do not fake migrations or reinstall reference SQL.

## Changed files

- Buyer forms/views and catalog/order templates: stricter filter validation, persistent category selections, inactive-seller checks, assessment history display.
- Account forms/views/template and response middleware: private validated profile editing and cache controls.
- Marketplace Order mapping, migration and adjacent SQL: immutable purchase assessment capture.
- Buyer, evidence and interface tests: filter edges, profile tampering/privacy, invalid screenshots, concurrent buyers, snapshot immutability and account layout.

## Validation

Scientific extension imports were unusually slow during initial runs; no fabricated scans were substituted. Fixtures use real fitted synthetic-model inference and disposable databases. Synthetic test results do not establish real-world fraud accuracy.


## Running the updated workflows

Use `.\scripts\start_demo.ps1 -WithWorker` with the existing configured trusted model and worker connection, or run `python manage.py runserver` and `python manage.py run_risk_worker` in separate terminals. Seller location changes can pause publication while their replacement scan is queued/running. Existing workers retain the same fencing protocol; no new process or training schedule is introduced by Step 6.


## Executed verification results

- Final full suite: `.\.venv\Scripts\python.exe -m pytest -q --disable-warnings --maxfail=2` with `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1`: **106 passed in 122.94 seconds**. Includes real PostgreSQL worker/fencing tests, actual fitted synthetic-model inference, separate-connection buyer and moderation races, restricted web-process roles, private evidence and participant checks.
- Browser coverage includes 18 page groups at 1440px and 360px, associated labels, overflow, keyboard/dialog behavior, polling recovery and upload feedback. Account screenshots were also visually inspected at both sizes: ignored `.local/ui-qa/account-desktop.png` and `account-mobile.png`.
- `manage.py check`: no issues. `manage.py makemigrations --check --dry-run`: no changes detected. Repository `python -m ruff check .`: all checks passed.
- Fresh migration installation verified by the disposable pytest database. Existing-data upgrade verified against the restored backup before working migration. `manage.py migrate --noinput` applied only `marketplace.0006_order_assessment_snapshot`; `showmigrations marketplace` confirms it applied. Working order count remains 1, with its historical snapshot correctly NULL.
- Initial test attempts exposed test-only setup/cleanup problems: self-blocking an administrator fails the audit guard; unmanaged tables need cascading transaction teardown; race fixtures must reseed flushed role groups and retain the full auth model registry. These were corrected and the final full suite above passed. Early native-library import stalls eventually resolved; no skipped or invented inference was substituted.

No remaining Step 6 implementation blockers. No working user purchases/reports were created for testing, and no commit, push or deployment was performed. The standalone reference SQL regression suite was not separately rerun in this step; application PostgreSQL race and process-privilege coverage ran in the final suite.
