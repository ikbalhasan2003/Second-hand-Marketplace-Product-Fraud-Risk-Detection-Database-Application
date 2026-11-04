# Database verification

**Verified:** 3 November 2026, Asia/Shanghai  
**Runtime:** PostgreSQL 18.6 on Windows x64, isolated disposable databases  
**Test client:** Python 3.12.16 and Psycopg 3.3.7  
**Static parser:** pglast 8.7

The proposed application baseline remains Python 3.13/Django 5.2. The database tests used the locally available Python 3.12 interpreter; this is not a Django compatibility or application acceptance result.

## Executed checks

| Check | Observed result |
| --- | --- |
| Fresh 001–005 installation | All table, index, foreign-key, trigger, function and view definitions executed on PostgreSQL 18.6 |
| 006 synthetic fixture | Committed successfully; no usable passwords, fabricated model artifact or evidence files |
| Integration suite | **25 tests passed** in the final run; includes two independent connections competing for one product |
| Optional 008 process grants | Executed successfully on the test database |
| Process privilege regression | Passed; permitted web publication/orders/audits and maintenance calls worked; direct role/history/audit/job writes and private worker/training reads were denied |
| Representative read queries | All 12 statements in `database/examples.sql` executed, including search and queue execution plans |
| Static SQL syntax | All numbered scripts, including optional vector DDL, parsed successfully; psql metacommands were checked by psql rather than the SQL parser |
| Generated documentation | 38 designed tables, 314 columns and 75 foreign keys represented across dictionary/schema and six Mermaid diagrams |
| Standard runtime catalog | 36 base tables, 299 columns, 72 foreign keys and 130 indexes, excluding the optional vector migration |

The final integration run installed the schema into a fresh database and reported `Ran 25 tests ... OK`. Ordinary test scenarios roll back. Its last race scenario commits a fourth synthetic listing and exactly one competing purchase. Test duration is a local regression result, not an application throughput or latency benchmark.

## Integrity scenarios covered

- Case-insensitive email identity, unique memberships and disjoint administrator/marketplace access.
- Invalid prices, currency mismatch, revision foreign keys, immutable listing/order/report targets and sealed image associations.
- Request replay/conflict, one-sale protection, actor/state transitions, terminal sales and cancellation preserving administrator removal.
- Canonical moderation corrections, historical cutoff selection and exclusion after an unresolved correction.
- Conversation participants, recipient-only receipts and blocked-account send restrictions.
- Atomic privileged audit: an intentionally failing audit insert rolls the associated action back.
- Unbound pending jobs, bound/unbound deduplication, frozen features, valid completion, one result and expired/replaced claim rejection.
- Snapshot-age/context/revision/model invalidation and permanently failed scans exposing no current low-risk score.
- Daily campaign replay advancing each context once; immutable models, rules and frozen datasets; cross-partition seller leakage rejection.
- Configured unanswered-order expiry, system history and repeatable expiration; blocked sellers retaining permitted existing fulfilment actions.
- Actual simultaneous purchase attempts: one commits and one receives the expected availability conflict.

See [the integration suite](../../database/tests/test_database.py) and [process privilege regression](../../database/tests/check_privileges.sql). [Setup instructions](../../database/README.md) explain how to reproduce them against a new empty database.

## Execution-plan sample

[EXPLAIN_SAMPLE.txt](EXPLAIN_SAMPLE.txt) contains the two actual plans from `database/examples.sql` against the tiny final verification fixture. At that point it had four products and four scan jobs. Planning choices and timings on this fixture do not establish the PRD's 10,000-listing or 10-concurrent-user targets. Load a realistic course dataset, run `ANALYZE`, and measure the stated workload before reporting performance.

## Remaining verification boundaries

The optional pgvector migration was syntax-checked but not executed because the server extension was unavailable. Vector operator/function usage follows the [official pgvector reference](https://github.com/pgvector/pgvector); extension availability and actual embedding/model compatibility still need their own installation test.

These database tests do not implement or verify the Django routes, browser object authorization, CSRF/session configuration, password hashing, throttling, decoded upload contents, external file immutability, real feature extraction, trusted model loading, model accuracy, scheduled deployment, backup restoration or the full application acceptance matrix. Runtime actor settings assume a trusted authenticated backend; process-role checks do not prove browser-user isolation. These boundaries remain explicitly assigned in the [design](../../DATABASE_DESIGN.md).
