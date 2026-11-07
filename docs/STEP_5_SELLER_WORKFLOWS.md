# Step 5 ? Seller workflows

Implemented on 6 November 2026. Existing local changes from Steps 1?4 were preserved.

## Submission and publication policy

`publish_listing` retains its internal service name for compatibility, but now means submit an immutable revision for scanning. The request validates fields and up to six decoded JPEG/PNG/WebP images, stores the revision/images and queues a durable job atomically. Photos remain optional; no arbitrary minimum was added. Incomplete private drafts neither change the submitted revision nor enqueue inference. Concurrent draft/revision edits return a conflict.

Public release is derived from `current_listing_risk`, rather than a second mutable publication flag. The current revision/context must have a successful job for the active compatible model/rules, with an unexpired feature snapshot. All three completed risk levels permit publication. High risk requires acknowledgement in the application checkout. A score indicates risk, never a fraud finding or safety guarantee.

Pending, scanning, failed and stale submissions are excluded from the catalog, public detail URLs and public image URLs. Checkout enforces the same gate in Python and a PostgreSQL insert trigger. No working database history is rewritten. Internal `available` records are candidates for publication, not proof of public eligibility; `first_published_at` retains its existing submission-time semantics for feature compatibility. Purchased historical terms remain readable to the purchaser even after eligibility changes.

An edit replaces the current submitted revision and invalidates the old result immediately. The listing remains hidden until the replacement scan succeeds. A late completion for an earlier revision cannot release current content. A model/rules change or expired snapshot pauses publication until current results exist. Existing rescanning campaigns/maintenance and worker fencing remain in use.

Without a compatible active model, jobs remain pending; missing/invalid artifacts produce failed scans through the real worker. The seller sees pending/scanning/failed/stale/ready and completed scores/reasons, with execution history and sanitized errors. Failed submissions can be corrected and resubmitted as a new immutable revision. Automatic worker execution retries retain the existing three-attempt policy; no request promises immediate inference.

Run `python manage.py run_risk_worker` with the configured worker connection and trusted registered/activated artifacts. See [worker operations](WORKER.md) and [model setup](ML_PIPELINE.md). For demo data, run the worker to successful completion, then rerun `python manage.py seed_demo`; seeding never bypasses scanning to create a new order.

## Ownership, images, messaging and archival

Seller edit, submission, withdrawal, draft images, assessments and revision history require the listing owner. Submitted image reads use the Django `/listing-media/` handler, including production. Unscanned/withdrawn/historical images require the owner, administrator or a buyer with the corresponding purchased/reported revision. Do not map the media directory directly to a static server.

Sellers reply through `/sell/conversations/`. Conversation pages, sends, polling and read receipts check the participant and selected role. Existing SQL guards enforce active message senders and retained messages. Blocked participants retain scoped reading and existing order obligations, but cannot create/edit listings or send messages.

Withdrawal archives through `removed_by_seller`, preserving revisions/images, messages, assessments and orders. Active orders prevent withdrawal; reserved/completed sales prevent material editing. Administrator removal cannot be undone by a seller.

## Order states and actors

| Display state | Retained database state | Allowed actions |
| --- | --- | --- |
| Pending, awaiting acceptance | `placed` | Seller accepts; either participant cancels or disputes; maintenance expires unanswered orders |
| Pending, accepted | `accepted` | Seller ships; buyer confirms an in-person handover/completion; either participant cancels or disputes |
| Shipped | `shipped` | Buyer confirms completion; either participant disputes |
| Completed | `completed` | Terminal |
| Cancelled | `cancelled` | Terminal; reservation is released without restoring removed visibility |
| Disputed | `disputed` | Administrator resolves to completed/cancelled with evidence and audited reason |

The Pending history filter includes both placed and accepted. Stored timeline events retain the precise phases. Actions require the expected current state and a reason. Participant checks, ordered locks, the unique active-sale constraint and immutable purchased revisions prevent cross-owner changes, stale transitions and double sales. Sales history uses ordered titles/prices, not mutable current content.

## Migration and recovery

Created and applied `marketplace.0005_scan_publication`, loading new `sql/007_scan_publication.sql`. It adds the eligibility function and scanned-purchase insert trigger without table/data changes, so no ORM state change is required. The trigger uses a fixed search path and definer rights; only the web process receives explicit eligibility-function access. `database/009_app_privileges.sql` includes the grant after the existing blanket function revocation in script 008.

The verified target was `secondhand_fraud` under the configured owner connection. A custom-format database backup is recorded in ignored `runtime/backups/STEP5_BACKUP_PATH.txt`. It was restored into a uniquely named disposable database, table counts were inspected and the upgrade succeeded there before the working migration ran. Working counts stayed at 5 users, 3 products, 3 revisions, 1 order and 0 risk results. Existing unscanned candidates now remain hidden; existing orders remain retained.

The migration is intentionally irreversible through Django. Recovery requires coordinated application/database rollback using the backup; never fake/unapply history or reinstall the reference schema. The backup covers PostgreSQL; media was not changed by migration and must remain coordinated in operational backups. Runtime configuration currently uses the owner connection; deploy with the documented separate process logins. Restricted web-role behavior is tested separately.

## Validation

See the verification results appended below after the final checks. The test scanner uses the real trained synthetic pipeline, actual feature extraction and fenced database functions in each isolated test transaction. Independent-connection worker tests also exercise lease renewal, failure and stale-result fencing. Synthetic evaluation is not evidence of real-world fraud accuracy.

## Changed files

- Listing/order services: `marketplace/services/listings.py`, `marketplace/services/orders.py`.
- Publication enforcement/schema/grants: `marketplace/migrations/0005_scan_publication.py`, `marketplace/migrations/sql/007_scan_publication.sql`, `database/009_app_privileges.sql`.
- Seller/buyer views and authorized media routing: `seller_app/views.py`, `buyer_app/views.py`, `config/urls.py`.
- Seller templates: `edit.html`, `dashboard.html`, `risk_content.html`, `revisions.html`; shared buyer `orders.html` and `components/order_snapshot.html`.
- Real feature extraction was factored into a cursor helper in `risk/features.py`; the worker entry point still owns its repeatable-read, read-only extraction transaction.
- Regression fixtures/coverage: `tests/conftest.py`, seller, buyer, evidence, delivery, interface, admin and demo integration tests.
- Demo provisioning: `accounts/management/commands/seed_demo.py`.
- Documentation: this guide, `README.md`, configuration/demo guides and `PROJECT_UPDATE_PLAN.md`.

## Executed verification results

- `.\.venv\Scripts\python.exe -m pytest -q --disable-warnings --maxfail=3`: **91 passed in 118.60 seconds**, including real PostgreSQL worker tests, restricted web-process role workflows, and Edge checks of 17 page groups at 1440px and 360px with labels, overflow, focus, chat polling and assessment refresh checks.
- Final `.\.venv\Scripts\python.exe -m pytest tests/integration/test_seller.py -q --disable-warnings`: **12 passed in 3.99 seconds**, including the final added cancellation/archival test and final seller display changes. The full run above preceded this one added test.
- `manage.py check`: no issues. `manage.py makemigrations --check --dry-run`: no changes detected. `python -m ruff check .`: all checks passed.
- Fresh migration installation exercised by pytest's disposable test database. Existing-data upgrade exercised against the verified restored backup before working migration. `manage.py migrate --noinput`: applied only `marketplace.0005_scan_publication` to the working target.
- Working operational state: **0 active models, 0 active rulesets, 3 queued scans**. No working scans or training were invented or triggered during this step. Activate a trusted compatible model/ruleset and run the configured worker to release these submissions. Existing order history is preserved. No implementation checks remain blocked.

Earlier test runs exposed assertions that assumed pending listings could be browsed or purchased; those fixtures now perform real synthetic fitted-model inference first. The browser refresh test now verifies retention of that completed score. An intermediate overlapping test invocation collided with the shared disposable test database; it was rerun sequentially and passed. No working database was reset, and no data, commits, pushes or deployments were performed outside the authorized migration/backup work.


## Runtime setup completed ? 6 November 2026

The earlier pending-model operational prerequisite is now resolved. Verified the existing locally produced `rf-synthetic-v1` artifact and its 5,000-record dataset, exact dependencies, checksums and evaluation metadata; registered dataset/model/ruleset IDs 1/1/1 and activated them through administrator ID 5 with activation audit ID 3. This is a synthetic prototype; real-world fraud accuracy remains unmeasured.

Created a dedicated non-superuser worker login with documented worker-only grants and stored its connection privately in ignored `.env`. A pre-activation database backup is retained under ignored `runtime/backups/step5_activation_before_20261106_030751.dump`. Activation campaigns were drained before completing inference. Seven historical/current jobs succeeded; all three current revisions are ready: listing 1 Low 38/100, listing 2 Low 38/100, listing 3 Medium 58/100. Historical order records were preserved.

Started the background risk worker and restarted the local web server at `http://127.0.0.1:8000/`. Verified HTTP 200 from the live homepage and all three listing pages. Process identities/start times and logs are in ignored `runtime/demo_processes.json`, `runtime/worker.*.log` and `runtime/web.*.log`. Use `scripts/stop_demo.ps1` to stop the managed processes. To restart after a reboot, use `scripts/start_demo.ps1 -WithWorker` after clearing stale records with the stop script. No operating-system autostart schedule was installed.
