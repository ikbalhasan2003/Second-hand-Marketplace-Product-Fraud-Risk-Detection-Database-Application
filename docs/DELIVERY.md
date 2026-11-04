# Delivery verification

This record separates implemented P0 behavior, executed checks and remaining acceptance gaps. The raw measured performance/recovery result is [evidence/delivery.json](evidence/delivery.json). The user-facing demonstration is [DEMO.md](DEMO.md); the project analysis is [ACADEMIC_REPORT.md](ACADEMIC_REPORT.md).

## Reproduce checks

Use Python 3.13, pinned `requirements/lock.txt`, PostgreSQL 18 and the setup described in [SETUP.md](SETUP.md). Configure `PGHOST`, `PGPORT`, `PGUSER` and `PGDATABASE` for a disposable local server. The test operator must be allowed to create isolated databases and a restricted test login. The verifier never resets an existing database or substitutes SQLite.

```powershell
$env:DJANGO_DEBUG = 'true'
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest -q
python -m ruff check .
python scripts/verify_delivery.py --pg-bin C:\path\to\PostgreSQL\18\bin
```

The existing direct database regression runs separately against an empty disposable database, followed by script 008 and the privilege regression. See [database verification](database/VERIFICATION.md). Do not run standalone `database/install.sql` over a Django-owned application database.

## Performance and restore method

The verifier creates three uniquely named isolated databases. The search source contains 10,000 actual synthetic product/revision/publication records, with real publication triggers and unbound durable jobs. Ten HTTP clients execute ten requests each across five warmed query variants. Timing includes Django middleware, view, template and PostgreSQL work, but excludes network/TLS and images. Every response must be HTTP 200; the target is p95 <=1 second. This is single-host course-scale evidence, not an internet load test.

The scan source is separate so the queue condition is truthful: one actual warmup inference loads the saved pipeline; twenty subsequent actual publications form the measured backlog. One reusable worker processes those twenty jobs. Latency is the database completion time minus each job's queue creation time, including waiting. The target is p95 <=15 seconds with at most twenty waiting jobs. The fitted pipeline and inputs remain synthetic-only.

With source writes and workers quiesced, the verifier dumps the scan source in PostgreSQL custom format and copies its referenced public/private media and trusted dataset/model trees as one recovery set. It restores a new database and separate storage roots, compares every copied file checksum, loads the verified fitted pipeline, checks table counts and historical links, and exercises restored order/report/evidence URLs as reporter, seller, unrelated buyer and administrator using a separate restricted web login. Role definitions are cluster-level prerequisites; table/function ACLs travel in the database dump. No real participant data enters the drill.

## Acceptance evidence map

| Criteria | Automated evidence | Assessment boundary |
| --- | --- | --- |
| AC-01 | Fresh Django migrations, schema mapping tests and direct SQL regressions | ORM/migration state, composite references, triggers/indexes/views |
| AC-02, AC-21, AC-22 | Account and role-isolation integration tests | Public registration cannot grant admin; app switching cannot enable roles |
| AC-03 | Seller publication/draft/revision/upload tests | Immutable content/images, version conflicts, atomic durable enqueueing |
| AC-04, AC-08 | Buyer search/filter and actual worker failure tests | Current Low only; pending/stale/failed never receive default scores |
| AC-05–07 | Actual fitted-worker PostgreSQL integration and direct database regressions | Frozen snapshots, replacement tokens, retries, changed configuration/freshness |
| AC-09–11 | Buyer/order integration plus independent two-connection database purchase race | Idempotency, state machine, immutable terms and visibility separation |
| AC-12 | Buyer/Seller participant/read-receipt tests | Private shared threads, unrelated access denied |
| AC-13 | Upload/evidence tests and restored restricted HTTP requests | Decoding/count/size limits, reporter/admin privacy, restricted-case evidence |
| AC-14–15 | Database correction/label/audit regression and Admin integration | Canonical chain serialization, unresolved exclusion and audit rollback |
| AC-16–18 | ML tests, immutable dataset/split manifest and measured three-model evaluation | Synthetic data only; real-world effectiveness not measured |
| AC-19 | Configuration/campaign database and worker tests | Version history, compatible activation and recoverable rescan obligations |
| AC-20 | Coordinated isolated restore and local demonstration instructions | Quiesced local recovery; online point-in-time recovery not tested |
| AC-23 | Cross-role automated workflows and the scripted manual demonstration | Full manual multi-browser demonstration remains a distinct check |

This mapping identifies the supporting checks. It does not silently mark every UI/manual acceptance item passed. Final executed counts, measurements and outstanding gaps are recorded below after the verification run.

## Remaining verification boundaries

Public deployment, TLS/proxy behavior, a hosted scheduler/service supervisor and an online restore exercise are outside the measured local run. Manual responsive/keyboard/browser testing must be recorded separately. Synthetic-only training has no real-world fraud accuracy or probability calibration evidence. Any unmet measured target must retain its actual result and corrective action in the committed evidence.
