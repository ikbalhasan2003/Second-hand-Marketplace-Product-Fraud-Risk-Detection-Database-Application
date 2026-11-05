# Full task verification and bug fixes

Executed 5 November 2026 (Asia/Shanghai) against the existing working tree. Existing uncommitted implementation changes were preserved. This audit covers the automated local scope of tasks 1 through 11 in `prompt.md`; it does not certify production deployment or human presentation sign-off.

## Coverage

| Tasks | Executed verification |
| --- | --- |
| 1: Configuration | Django system checks, configuration-dependent account/upload/risk tests |
| 2: Django foundation | System checks, migration drift, fresh test database migrations |
| 3: PostgreSQL integration | Schema tests, 25 standalone database regression tests, separate SQL privilege regression |
| 4: Accounts | Registration, authentication, session, role and ownership integration tests |
| 5: Seller | Publication, revisions, uploads, conflicts and ownership integration tests |
| 6: Buyer/shared workflows | Search, orders, conversations, reports, private evidence and continuous cross-app scenario |
| 7: Dataset/model | ML unit tests and repeated 5,000-record generation/training/evaluation |
| 8: Risk worker | Real fitted-worker integration, leases, recovery, fencing and freshness checks |
| 9: Admin | Authorization, moderation, audit rollback, correction chains and model activation tests |
| 10: Interface | Edge checks of all 17 page groups at 1440px and 360px, labels, keyboard, polling, drafts and uploads |
| 11: Delivery | Search/scan measurements and coordinated database/media/artifact restore with restricted HTTP access |

## Bugs corrected

- Risk refresh checked focus only before fetching. If focus entered the panel during the request, replacement removed the focused control. A new Edge regression reproduced the failure. The script now checks focus, document visibility and open dialogs again after receiving the response and defers replacement when necessary.
- Chat polling and read endpoints accepted IDs outside PostgreSQL's signed bigint range. A regression demonstrated an invalid cursor receiving HTTP 200. Poll cursors, read-through IDs and explicit read IDs now reject values above `2**63 - 1` with HTTP 400; existing recipient and ownership checks remain covered.

Changed implementation: `buyer_app/views.py`, `static/risk.js`. Regression coverage: `tests/integration/test_buyer.py`, `tests/integration/test_interface.py`.

## Measured delivery result

Final complete application/unit/worker/Edge suite after fixes: **70 passed in 108.65 seconds**, with no skipped tests. The earlier baseline suite passed 69 tests before the new cursor regression was added. The new focus regression failed before the JavaScript fix and passed in the final full suite. Focused buyer verification also passed all 6 tests.

Final delivery run: `20261104173026_2115c7e1`. Raw evidence including source hashes is retained locally at `.local/retest-delivery-final.json`; recovery files are under `runtime/delivery/20261104173026_2115c7e1/`.

- Search: 10,000 listings, 10 clients, 100 successful HTTP requests; p95 **0.280 seconds**, target <=1 second.
- Warm worker: 20 waiting jobs; p95 **1.484 seconds**, target <=15 seconds.
- Restore: **33 checks passed**, including file checksums and restricted HTTP ownership.
- Reproducibility: generated records, every prediction probability, complete evaluation and pipeline bytes identical across repeats. Data remains synthetic-only.
- Standalone database regression: **25 passed**. Separate fresh SQL install, seed, process grants and `check_privileges.sql` all passed.
- Django system check: no issues. Migration drift: no changes detected. Ruff: all checks passed.

The initial run without local environment configuration stopped at the required secret setting. Subsequent runs explicitly used local debug mode and the disposable PostgreSQL operator on port 55432. No existing application database was reset. A focused test attempt overlapped the full suite's test database and failed at database setup; it was rerun with its own isolated test database.

## Remaining boundaries

A human-operated three-profile demonstration, production TLS/proxy/scheduler behavior and online point-in-time recovery remain outside these checks. Model metrics do not establish real-world fraud accuracy. See `DELIVERY.md` and `DEMO.md` for those acceptance boundaries.
