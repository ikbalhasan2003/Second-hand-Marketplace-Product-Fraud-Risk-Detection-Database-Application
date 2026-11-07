# Step 3: shared marketplace entry points

Implemented 6 November 2026.

- `/` serves the public catalog directly. `/listings/` remains a public catalog/search URL; listing details, buyer orders, messages, reports and private evidence use their corresponding paths under `/`.
- `/sell/` contains the seller dashboard, listing management, sales and seller conversations. Both roles share the marketplace header, account page and authentication entry points.
- `/login/` accepts existing buyer or seller membership without granting roles. Seller-only members default to `/sell/`; buyers and dual-role members default to `/`. Safe `next` destinations preserve deep links; foreign hosts, network URLs and HTTPS downgrades are rejected.
- `/register/` uses the existing registration fields with an explicit buyer/seller selection. Administrator selection is denied. Seller onboarding and sole-admin provisioning remain Step 4 work.
- `/admin-app/` requires active administrator membership and uses `/admin-app/login/`. There is no public admin registration.
- Legacy `/buyer-app/` and `/seller-app/` GET/HEAD routes redirect to canonical equivalents with query strings preserved. Unknown legacy paths return 404. Legacy login/register bookmarks use shared auth; seller registration bookmarks preselect seller.
- Legacy unsafe requests execute the matching original handler with the original method, body, uploads, session and CSRF check. They never redirect before executing an action. Existing successful POST handlers return their normal canonical result redirect. Old authentication POSTs preserve their original membership selection.
- Anonymous protected deep links lead to shared login; wrong-role sessions receive 403. Object ownership and participant checks remain enforced. Blocked members retain history and existing-obligation access, while existing active-membership checks continue to deny new purchases, listing edits and messaging. Admin access requires active status.

Changed areas: `config/urls.py`, `config/settings.py`, `accounts/{access,context,views}.py`, buyer redirect/auth handling, affected templates, canonical URLs in integration tests, startup/delivery scripts, README and architecture route examples. No outbound email link generation was found in the application.

No schema changes or migrations were created or applied. Working marketplace records were not modified. Tests use Django's disposable PostgreSQL test database. Existing unrelated local changes were preserved. To revert routing, restore these application/template/script changes together; there is no data rollback.

## Verification

- `python manage.py check`: passed.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `python -m ruff check .`: passed.
- `git diff --check`: passed (existing line-ending notices only).
- Focused routing/account/buyer regression run: 21 passed.
- Initial integration run excluding the browser check: 68 passed, one anonymous deep-link failure; fixed with login decorators and verified in the focused run.

- Final `python -m pytest tests -q --disable-warnings`: **79 passed in 110.82 seconds**, including the Edge browser test of 17 page groups at 1440px and 360px, dialog keyboard handling, polling recovery, drafts and upload feedback. Mobile marketplace screenshot also inspected directly.
- During development, an overlapping focused test invocation hit an already-in-use disposable test database; it was rerun sequentially. An earlier broad run was interrupted. Neither is counted as successful validation; the final complete run above is authoritative.

No remaining Step 3 blockers. No startup command changes: use the existing `scripts/start_demo.ps1` or `python manage.py runserver`; the startup script now prints canonical marketplace/seller URLs.
