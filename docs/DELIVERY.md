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

Public deployment, TLS/proxy behavior, a hosted scheduler/service supervisor and an online restore exercise are outside the measured local run. Automated Edge layout/keyboard/polling checks and mobile screenshot inspection are recorded below; a human-operated multi-profile demonstration remains separate. Synthetic-only training has no real-world fraud accuracy or probability calibration evidence. Any unmet measured target must retain its actual result and corrective action in the committed evidence.

## Final executed verification

Verified locally at **2026-11-05 01:17:31 +0800 (Asia/Shanghai)**. The performance/recovery run is `20261104171731_d5fe5630`; [delivery.json](evidence/delivery.json) records the environment, working-tree source hashes, isolated database names, storage checksums and actual measurements. The tree contains uncommitted work, so the recorded Git HEAD alone is not the tested source identity. [verification.json](evidence/verification.json) records test accounting and the acceptance map.

| Executed check | Actual result |
| --- | --- |
| Django system checks | No issues |
| Migration/model drift | No changes detected; confirmed against the restored migrated database |
| Full application/unit/worker/browser suite | 68 passed in 110.46 seconds |
| Newly added continuous cross-app acceptance scenario | 1 passed in 1.13 seconds, executed separately after the full run |
| Ruff | All checks passed |
| Search: 10,000 listings, 10 clients, 100 requests | p95 0.270 s against <=1 s; all HTTP 200 |
| Warm inference: one worker, 20 waiting jobs | p95 1.235 s against <=15 s |
| Coordinated isolated restore | All 33 recorded checks passed; public/private/artifact checksums and restricted HTTP ownership verified |
| Reproducibility | 5,000 generated records, every inference probability and complete evaluation identical; pipeline bytes also identical |
| Optional browser verification | Executed in Edge: all 17 groups at 1440px/360px; labels, overflow, keyboard dialog/focus, polling/drafts/scroll, deduplication and upload feedback passed |

Mobile catalog and model-management screenshots were inspected from ignored `.local/ui-qa/`. The full suite and focused test are separate executions; the total is not described as a 69-test full-suite run. The initial migration-drift command named an absent disposable database and warned that history could not be checked; it was rerun successfully against the migrated restore target.

### Criterion-by-criterion assessment

Each row means verified within the stated local automated scope, rather than a claim about public deployment or real fraud outcomes. Prior standalone database evidence is explicitly reused from [database/VERIFICATION.md](database/VERIFICATION.md): 25 tests and process grants/privilege checks dated 3 November 2026. That historical direct SQL run was not rerun in this delivery; current Django/PostgreSQL, restricted-role, worker and restore checks were executed again.

| Criterion | Local result | Supporting evidence |
| --- | --- | --- |
| AC-01: Fresh PostgreSQL installation/schema | Automated checks passed | test_schema.py; prior direct SQL catalog/dictionary evidence |
| AC-02: Identity and authorization | Automated checks passed | test_accounts.py; test_admin.py restricted web-role HTTP |
| AC-03: Immutable publication and revisions | Automated checks passed | test_seller.py; test_uploads.py |
| AC-04: Visible search and current Low filtering | Automated checks passed | test_buyer.py; test_interface.py; 10,000-listing measurement |
| AC-05: Worker unavailable/recovery | Automated checks passed | test_worker.py actual unbound/publication/worker inference |
| AC-06: Repeated execution and fencing | Automated checks passed | test_worker.py real PostgreSQL lease/token/retry checks |
| AC-07: Late results and freshness | Automated checks passed | test_worker.py; reused direct SQL configuration/currentness tests |
| AC-08: Explicit failed/unassessed display | Automated checks passed | test_interface.py unfinished states; test_worker.py terminal failures |
| AC-09: Competing and repeated purchases | Automated checks passed | test_buyer.py request replay; reused two-connection database purchase race |
| AC-10: Order state machine/history | Automated checks passed | test_buyer.py; test_delivery.py; reused direct SQL invalid-transition tests |
| AC-11: Cancellation, removal and final sale | Automated checks passed | test_buyer.py; test_seller.py; reused direct SQL sale constraints |
| AC-12: Conversation privacy and receipts | Automated checks passed | test_buyer.py; test_interface.py polling/deduplication; test_delivery.py |
| AC-13: Private decoded evidence | Automated checks passed | test_uploads.py; test_evidence.py; restored restricted HTTP checks |
| AC-14: Canonical labels and corrections | Automated checks passed | test_admin.py concurrent correction/unresolved exclusion |
| AC-15: Audit atomicity | Automated checks passed | test_admin.py forced audit failures for moderation, correction and dispute |
| AC-16: Saved-model reproducibility | Automated checks passed | test_ml.py; delivery.json regenerated 5,000 records, retrained predictions/evaluation |
| AC-17: Dataset provenance and leakage | Automated checks passed | test_ml.py; test_worker.py point-in-time selection; manifest checks |
| AC-18: Three-model measured evaluation | Automated checks passed | delivery.json reproducibility.test_metrics; ML_EVALUATION.json synthetic-only metrics |
| AC-19: Audited configuration/rescans | Automated checks passed | test_admin.py real artifact activation; test_worker.py maintenance; test_interface.py rescan receipts |
| AC-20: Coordinated recovery and local delivery | Automated checks passed | delivery.json restore all checks; SETUP.md; DEMO.md; test_demo.py |
| AC-21: Three application entry points | Automated checks passed | test_interface.py all 17 groups in Edge; account/admin route tests |
| AC-22: Application-role isolation | Automated checks passed | test_accounts.py; test_admin.py; test_seller.py ownership checks |
| AC-23: Continuous cross-application workflow | Automated checks passed | test_delivery.py one continuous three-session HTTP scenario |

### Open acceptance and delivery boundaries

No failing automated P0 criterion or measured performance target remains in the executed scope. **Human presentation sign-off for AC-20 and AC-23 remains open:** the core flow has been rehearsed through independent HTTP sessions, and restored pages were exercised under a restricted web login, but a person has not yet completed and recorded the entire three-browser-profile walkthrough. [DEMO.md](DEMO.md) provides the exact rehearsal and keyboard/mobile checklist.

Production TLS/reverse-proxy behavior, service supervision, hosted scheduling, online point-in-time recovery and optional P2 pgvector installation remain unverified. Model metrics remain synthetic-only, with no real-world accuracy/calibration claim. These are explicit boundaries, not silently passed requirements. Generated databases and recovery files are retained under the run workspace for inspection; no existing application database was reset.
