# Step 2: marketplace interface redesign

Implemented 6 November 2026 (Asia/Shanghai).

## Scope and routes

The public catalog at `/buyer-app/` and `/buyer-app/listings/` now acts as the storefront homepage. The existing `/` redirect remains intact as required by Step 2. Serving the homepage directly at `/` and consolidating authentication/navigation destinations remain Step 3 work. Existing form actions, protected media handlers, permissions, revision snapshots, purchase confirmation, polling and CSRF behavior are preserved.

## Delivered

- Shared Secondhand Market brand, marketplace navigation and separate moderation navigation. Administrator navigation contains case review, rules/models, audit and exports; no public administrator registration link.
- Responsive storefront introduction, prominent GET search, database-backed category navigation, persistent advanced filters, result counts, pagination and actionable empty/invalid-search states.
- Product cards use actual stored images and display currency/price, condition, location, availability, seller and honest risk state. Historical listings without photos retain a no-photo state; failed image requests display Photo unavailable. No stock photos, invented reviews, trust claims, transactions or metrics were introduced.
- Consistent panels, typography, controls, tables, focus treatment and responsive styles across buyer history/messages/reports, seller dashboard/listing editing, account/authentication and moderation pages. Product details include an at-a-glance price/condition/location panel alongside the existing assessment and purchase review.
- Search and forms retain server validation, associated labels, error summaries, keyboard focus, submission progress, upload feedback, polling recovery and no-JavaScript behavior. Advanced filters open automatically when a query or validation error is present.
- Fixed shared navigation enhancement so category query links are not all incorrectly marked current.

## Validation

Django system checks, compilation of all templates, Ruff on changed Python, and migration consistency checks pass. No migrations were created or applied. Tests use disposable PostgreSQL test records, not production account/listing mutations.

The existing interface suite passed 13 tests after the first redesign. It renders 17 real Django page groups in headless Microsoft Edge at 1440px and 360px, checking horizontal overflow, labels, one primary heading, purchase-dialog keyboard focus, chat draft/polling recovery, risk refresh failures, validation focus and upload validation. Browser requests use actual Django test-client responses and local CSS/JavaScript rather than mock page markup. Mobile screenshots were visually inspected; this exposed an incorrect category-current enhancement and an overly long initial filter panel, both corrected.

Local screenshots: `.local/ui-qa/` (test artifacts, intentionally untracked).

## Later-step dependencies

- Step 3: directly render `/`, consolidate shared sign-in destinations and handle legacy routes. Role-specific authentication endpoints intentionally remain.
- Step 4: simplified buyer registration, seller onboarding and editable profile/contact details. Account UI only exposes currently implemented password and membership operations.
- Step 5: scan-before-publication policy and any required minimum-photo rule. Current publication behavior remains unchanged; pending/failed/stale scans are never labelled safe.
- Step 6: additional browsing/purchase/report behavior and profile editing; location remains an exact case-insensitive match, now explained beside filters.
- Steps 7-9: additional moderation/user inspection, appeals and durable training controls. Existing administration pages show only recorded state and supported operations.

No database/schema changes, worker changes, account provisioning, commits or deployment were performed.

Commands used:

```powershell
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
.venv/Scripts/ruff.exe check buyer_app/views.py tests/integration/test_interface.py
.venv/Scripts/python.exe -m pytest tests/integration/test_interface.py -q
.venv/Scripts/python.exe -m pytest tests/integration/test_interface.py -q -k 'storefront_preserves or all_17'
git diff --check
```

All repository HTML templates were also compiled using Django's template loader. Final focused test results are recorded below.

Final results:

- Full existing interface suite: **13 passed** (85.79 seconds) after search/category fixes.
- Final 17-page browser check with desktop/mobile screenshot capture: **passed**.
- Added uploaded-photo/condition/category regression: **1 passed** (0.92 seconds). Initial attempts failed due to the test media URL binding and an unhashable test URL configuration; the final test binds a module-based URL configuration to its temporary directory. No production media-route change was needed. This checks Django development media delivery; deployment web-server media configuration remains an operational prerequisite.
- Final Ruff and `git diff --check`: passed. Django system check: no issues. Migration consistency: no changes detected. All template compilation: passed.
- Visually reviewed storefront and admin screenshots at desktop/mobile widths. No viewport overflow was detected across the 17 page groups. Scrollable moderation tables remain horizontally scrollable within their labelled region.
