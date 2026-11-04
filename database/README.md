# PostgreSQL database package

Start with the [database design](../DATABASE_DESIGN.md), [ER diagrams](../docs/database/ER_DIAGRAM.md), [relational schema](../docs/database/RELATIONAL_SCHEMA.md) and [data dictionary](../docs/database/DATA_DICTIONARY.md).

This package implements the database reference for the shared Admin, Buyer and Seller applications. It contains 36 standard tables, including authentication infrastructure and the two P1 extension structures, plus two optional embedding tables. SQL views supply the requested `fraud_logs` and `risk_score_history` interfaces over the single authoritative `risk_logs` prediction table. `review_embedding` is an optional P2 table for moderation-review text.

## Files and execution order

| File | Purpose | Apply by default? |
| --- | --- | --- |
| `install.sql` | psql entry point; applies 001 through 005 with stop-on-error | Yes |
| `001_core.sql` | Configuration, identities/permissions/sessions, catalog, orders, chat, reports, moderation, audit, appeals and notifications | Yes |
| `002_risk.sql` | Feature contracts, provenance, datasets/splits, models/evaluations, rules, jobs/results and rescan campaigns | Yes |
| `003_core_functions.sql` | Validation, immutability, audit and transactional order functions | Yes |
| `004_risk_functions.sql` | Configuration activation, queue triggers, lease-protected worker APIs, campaign batches and risk views | Yes |
| `005_views.sql` | Effective decisions, label candidates, administrator queue and seller order history | Yes |
| `006_seed.sql` | Small synthetic, non-login course fixture | Optional; fresh databases only |
| `007_embeddings_optional.sql` | pgvector extension and embedding-model/review-vector tables | P2 only |
| `008_privileges.sql` | Separate web, worker, maintenance and training process privileges | Recommended for deployment; requires role-management rights |
| `examples.sql` | Read queries and two `EXPLAIN (ANALYZE, BUFFERS)` examples | After seed |
| `tests/test_database.py` | PostgreSQL integration tests, including a two-connection purchase race | Disposable empty database |
| `tests/check_privileges.sql` | Process-role allow/deny regression checks, rolled back afterward | After seed and 008 |

Each numbered SQL file runs inside a transaction. Installation is intended for an **empty database**; these are initial DDL scripts, not idempotent upgrades. If installation fails, correct the problem and use a new empty database rather than rerunning individual `CREATE TABLE` statements over a partial installation. The optional files are deliberately excluded from `install.sql`.

## Build a demonstration database

Use PostgreSQL 18 with its `psql` and `createdb` utilities available on PATH. Run from the repository root. Connection credentials belong in your PostgreSQL connection configuration; the repository contains no database passwords.

```powershell
createdb --username postgres secondhand_fraud
psql --username postgres --dbname secondhand_fraud --file database/install.sql
psql --username postgres --dbname secondhand_fraud --set ON_ERROR_STOP=1 --file database/006_seed.sql
psql --username postgres --dbname secondhand_fraud --set ON_ERROR_STOP=1 --file database/examples.sql
```

The initial `marketplace_settings` row explicitly configures USD, a 48-hour unanswered-order timeout and the `Asia/Shanghai` refresh timezone. Choose the deployment currency **before creating revisions**. Historical revision prices retain their currency and a guard prevents changing the configured currency once revisions exist. Example locations and currency do not establish a real deployment geography.

The seed creates five categories, one administrator, one seller, two buyers, three products, a conversation, an order, two reports and one simulated moderation decision. Every person and event is synthetic. Password `!` is unusable in Django; the fixture does not provision working logins. No trained model or actual image/evidence file is fabricated. Published listings therefore start with queued unbound scans and pending risk, rather than an invented score.

The runnable Django application uses **Django migrations as its sole installation authority**. Run `python manage.py migrate` on a separate empty application database; do not run this reference bootstrap there. Django owns identity/authentication infrastructure and frozen SQL migrations install the domain schema with synchronized unmanaged ORM state. See [the migration strategy and executed verification](../docs/MIGRATIONS.md). Composite revision references retain both fields and SQL constraints. The [design's Django mapping section](../DATABASE_DESIGN.md#10-django-mapping-and-migration-ownership) explains the boundary.

## Transaction and actor contract

The web backend authenticates the person, authorizes the action, begins a transaction, and sets transaction-local actor context from trusted session data:

```sql
BEGIN;
SELECT set_config('app.actor_id', '3', true);
SELECT set_config('app.action_reason', 'Buyer placed an order', true);
SELECT place_order(
    3, 102, 1,
    '00000000-0000-4000-8000-000000000123'::uuid,
    repeat('a',64) -- example only: the service computes a canonical request SHA-256
);
COMMIT;
```

The request key is unique per buyer. Replaying the same key and facts returns the original order; different facts produce a conflict. The transaction owns the product lock while the order, reservation and history event commit together. Use `transition_order(order_id, next_status)` for subsequent transitions; it locks product before order and triggers actor/state validation and history creation.

`app.actor_id` is a **trusted-backend assertion**, not database authentication of the browser user. A person possessing the pooled web database credentials could set it themselves. Keep those credentials in the server and enforce ownership on every HTTP request. Views do not implement row-level authorization. No browser or client connects directly to PostgreSQL.

For operations involving account status and a listing, acquire affected user locks in ascending ID order, then the product, then order/review rows. `place_order` handles participant/product locking and request replay. Configuration changes take a shared advisory lock; worker APIs lock jobs without taking product locks. Handle a deadlock by retrying the whole idempotent service transaction with a bounded retry count.

Create each revision and all of its image associations in the **same transaction**, then advance the product pointer. The server-managed `created_xid` prevents later transactions from adding images to historical revisions. Storage objects must also be immutable; SQL cannot stop a filesystem process overwriting bytes at a storage key.

## Worker and maintenance APIs

| API | Transaction contract |
| --- | --- |
| `claim_risk_job(lease)` | Short claim transaction; compatible model/ruleset bound together, fresh token, bounded attempts and live lease |
| `save_risk_snapshot(job, token, as_of, snapshot)` | Persist point-in-time evidence under a live claim; retries must reuse the same snapshot |
| `heartbeat_risk_job(job, token, lease)` | Extend an unexpired current claim |
| `fail_risk_job(job, token, error_code, retryable)` | Sanitized failure; bounded retry or terminal failure |
| `complete_risk_job(job, token, score, factors, explanation)` | Under a live claim, insert one result and mark success atomically |
| `activate_risk_configuration(model, ruleset)` | Active administrator + reason; serialize activation, audit and create durable rescan obligations |
| `request_risk_rescan(product, request_uuid)` | Idempotent administrator request with a reason and typed audit target |
| `create_daily_rescan(date, timezone)` | Deduplicate one campaign per explicit date/timezone; null timezone uses configured timezone |
| `run_rescan_batch(campaign, limit)` | Freeze scope/cutoff; advance context once per campaign/product; persist cursor and receipts atomically |
| `expire_unanswered_orders(limit)` | Maintenance-only bounded batch; expire only `placed` orders older than configured timeout |

Commit a claim quickly, extract database features in a consistent read snapshot, save them under the claim, commit, then run inference outside long-held database locks. All subsequent writes carry that claim token. Use a heartbeat before expiry for long work; an expired worker cannot renew or finalize. At-least-once execution yields one committed result per job. Neither queue triggers nor SQL functions train or run a classifier.

`current_listing_risk` evaluates revision, context, active configuration, feature schema and snapshot age at read time. Its current score columns are null unless the state is `ready`. The low-risk query explicitly requires `ready` plus `low`; an old low score cannot qualify while reassessment is pending or failed.

Run maintenance through an external scheduler, initially daily for refresh and frequently enough for unanswered-order expiry. Publication remains durable while a worker is stopped. The SQL supplies work storage/APIs; the worker loop, consistent feature extractor, actual trained artifact and OS schedule remain application work.

## Process privileges

Create application objects using a dedicated non-login owner, with migration access controlled separately. Run `008_privileges.sql` with the required role-management privileges, then provision separate login roles and grant each the appropriate group role:

| Group role | Intended process |
| --- | --- |
| `secondhand_web` | Trusted Django backend; per-user authorization stays in the backend |
| `secondhand_worker` | Feature reads and EXECUTE-only claimed job mutations |
| `secondhand_maintenance` | Bounded refresh campaigns and unanswered-order expiry |
| `secondhand_training` | Read-only approved dataset/export metadata; no live contacts, chats or evidence |

The script revokes public schema creation and default function execution, blocks direct history writes from the web role and blocks raw job/result writes from the worker. Trigger-owned audit/history/queue operations use narrowly defined owner execution with a fixed search path. Do not grant the private claim helper or blanket function execution to runtime roles.

Auth groups, administrator provisioning, trusted feature/model registration, dataset export and deployment settings stay under controlled management credentials. `enable_marketplace_role('buyer'|'seller')` permits only an active authenticated account's explicit marketplace-role addition. It cannot grant administrator access or combine administrator and marketplace roles. The Admin App can author draft rules and activate compatible approved model/rule versions.

The included infrastructure models do not constitute configured Django sessions, CSRF, password hashing or rate limiting. Use Django password/session APIs, configure the specified bcrypt-backed hasher, and implement shared login/message/listing/report throttling. Authentication disablement (`is_active`) and marketplace blocking (`status`) have separate meanings.

## Optional embeddings

Install a compatible pgvector server extension before applying `007_embeddings_optional.sql`. It creates `embedding_models` and `review_embedding` using `vector(384)` with versioned text policy, content hash and unique review/model lineage. The dimension is an explicit research migration choice, not an assumed P0 model feature. Compare vectors only within the same embedding-model version. The optional script contains an exact cosine query and an example per-model HNSW index for later measured use. See [pgvector's official reference](https://github.com/pgvector/pgvector).

The extension migration was syntax-parsed but **not executed** in this verification environment because pgvector was not installed. All core tests use ordinary PostgreSQL without the extension.

## Run the regression suite

Install the small test dependency into your project environment:

```powershell
python -m pip install -r database/tests/requirements.txt
createdb --username postgres secondhand_fraud_test
$env:DATABASE_TEST_DSN = 'host=localhost port=5432 user=postgres dbname=secondhand_fraud_test'
python database/tests/test_database.py
```

The suite refuses a database with existing public tables. It installs 001 through 006, rolls back ordinary scenarios, and leaves a committed synthetic fixture for the independent-connection concurrency test. Use a different empty database for the next full run. It exercises PostgreSQL behavior directly; SQLite is not a substitute.

Run the separate process-privilege regression as the test/migration owner:

```powershell
psql --username postgres --dbname secondhand_fraud_test --set ON_ERROR_STOP=1 --file database/008_privileges.sql
psql --username postgres --dbname secondhand_fraud_test --file database/tests/check_privileges.sql
```

See [verification evidence](../docs/database/VERIFICATION.md) for the measured result and remaining checks. The tests use explicitly non-loadable AI metadata to test database relationships; they neither run a classifier nor measure fraud-detection accuracy.

## Keep the documentation synchronized

After changing table definitions, regenerate the physical dictionary, relational schema and six editable Mermaid diagrams:

```powershell
python docs/database/generate_reference.py
```

The generator uses the standard library. SQL remains authoritative; review the generated relationships and the prose normalization argument after each design change. Reference scripts are not yet Django migration files.
