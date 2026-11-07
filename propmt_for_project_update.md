# Project update prompts

Run these prompts in order. Each prompt is an implementation task, not a request for a proposal. Complete and verify each step before moving to the next. The source requirements are in `Problem for update.txt`.

## Shared instructions for every step

You are updating the existing Django/PostgreSQL project at `D:\SecondHandFraudDB`. Read applicable `AGENTS.md` files and inspect the relevant code before editing. Preserve unrelated local changes and existing data. Extend existing services, permissions, SQL functions, and UI components where possible instead of building duplicate systems.

Read `README.md`, `PRD.md`, `ARCHITECTURE.md`, `DATABASE_DESIGN.md`, and relevant documentation as needed. Follow `docs/MIGRATIONS.md`: Django migrations are the application installation authority. SQL-owned unmanaged domain models require new SQL migrations plus synchronized ORM/migration state. Never modify applied migration snapshots, fake migrations, reset the database, or install the standalone reference schema over the application database.

You are authorized to make necessary application and database schema changes. Inspect the configured database target without exposing credentials. Preserve existing records, use additive or carefully staged migrations, and document rollback/recovery implications. Do not drop existing data to simplify implementation. Do not print `.env`, passwords, tokens, or private user evidence. Keep secrets out of committed source, logs, and documentation.

Enforce permissions on the server for every action, including direct requests and file access. Keep CSRF protection, password hashing, upload validation, audit history, transaction safety, and existing risk-worker fencing intact. AI risk results indicate risk rather than establish fraud. Never invent successful scans, training results, or test evidence.

For each step, implement the change, run appropriate checks, and report changed files, actual validation results, any migration applied, and remaining blockers. Ask for clarification only when information is necessary and cannot be established from the repository. Do not expand this project into payment processing or unrelated services.

## Step 1 — Audit requirements and existing implementation

Read `Problem for update.txt` and inspect the existing account, buyer, seller, admin, marketplace, risk, ML, database, template, static asset, and test code. Map every requested feature to its current implementation. Identify working features, incomplete features, defects, and missing features with file references. Inspect migration history, database constraints, role provisioning, process privileges, risk scanning, and model training/activation workflows without exposing secrets.

Save a requirements checklist and dependency-aware implementation plan to `docs/PROJECT_UPDATE_PLAN.md`. Include proposed table changes, data preservation strategy, acceptance criteria, and the order in which later steps depend on one another. Record the intended two public entry points as `/` for the shared marketplace and `/admin-app/` for administration; nested buyer/seller workflows may exist within the marketplace. Interpret the admin requirement as one provisioned administrator with sign-in only and no public admin registration. Distinguish viewing an account's information from impersonating that user. Make no application or database mutations during this audit.

## Step 2 — Redesign the ecommerce interface

Use the Step 1 findings to redesign the existing templates and styles into a coherent, professional second-hand ecommerce marketplace. Implement a public homepage, clear branding, shared header, search, category navigation, product cards with real images, readable prices, location and condition details, risk badges, and useful empty/loading/error states. Improve product details, authentication, account pages, buyer/seller dashboards, and admin pages consistently. Keep the admin navigation appropriate to moderation work.

Use existing local assets and components where suitable. Do not introduce fake reviews, sales, trust claims, or placeholder transactions as real content. Preserve existing routes and behavior until Step 3 changes routing. Ensure keyboard access, visible focus, associated form labels, useful validation, adequate contrast, and responsive layouts at mobile and desktop widths. Verify real rendered pages and critical interactions, and resolve overflow or broken layouts. Record any flows requiring later steps.

## Step 3 — Consolidate the two main entry points

Implement `/` as the public marketplace homepage and `/admin-app/` as the protected administrator entry point. Buyers and sellers must share marketplace navigation and authentication entry points, with role-appropriate dashboards and actions after login. Two main entry points does not mean limiting the application to two total URLs.

Inspect all URL configurations, redirects, login destinations, navigation links, email links if present, and tests before changing routes. Organize buyer and seller workflows under the shared marketplace consistently. Preserve safe redirects from legacy `/buyer-app/` and `/seller-app/` links where practical, without redirecting mutation requests in a way that loses or repeats actions. Prevent open redirects and ensure anonymous, buyer, seller, blocked, and admin sessions receive the correct access. Verify deep links and direct unauthorized requests.

## Step 4 — Update accounts, onboarding, and the sole administrator

Implement simple buyer registration using email and password, with any display identity generated or collected without imposing unnecessary fields. Implement more formal seller onboarding with clearly justified profile/contact fields and server-side validation. Preserve existing accounts and role memberships, and explicitly define how an existing buyer becomes a seller without duplicating identities. Support shared marketplace sign-in and role-appropriate navigation.

Provision the single administrator using the email and password supplied in `Problem for update.txt`; read those values locally without repeating the password in output or adding it to committed files. Use Django password hashing and controlled provisioning rather than a hard-coded authentication bypass. Inspect existing administrators first. If several exist, preserve their records and resolve administrator membership through a reviewed, audited transition rather than deleting users or silently locking out the only working administrator. Make sole-admin provisioning idempotent and prevent regular users from obtaining admin privileges through forms, APIs, role changes, or direct requests. Do not expose public admin registration or routinely reset the admin password on startup.

Add necessary migrations for onboarding fields or invariants and update provisioning documentation. Verify registration, duplicate emails, password validation, login/logout, role separation, and admin provisioning behavior.

## Step 5 — Complete seller listing, messaging, and order workflows

Complete seller listing creation/editing with title, description, category, price, condition, location, and multiple validated product images. Preserve immutable revisions and historical order snapshots. Enforce ownership on every listing, image, conversation, and order mutation. Sellers must be able to manage their own listings, reply to buyer messages, view sales history, and inspect previous listing risk results.

Implement a scan-before-publication workflow: submission queues or runs the real configured risk pipeline, shows an honest pending/scanning state, and then displays score, level, and available reasons. Publish only when the defined publication policy permits it. Handle unavailable models, scan failures, edits during scanning, and stale results. Do not label unscanned listings as safe or promise instantaneous inference when work is asynchronous.

Support the required order states pending, shipped, completed, and cancelled, mapping them carefully to existing transactional order states. Define allowed transitions and who can perform them; prevent double sales, invalid transitions, and changes to another seller's orders. Use archival/removal behavior for listings when physical deletion would damage history. Verify uploads, ownership, scan/publication behavior, messaging, and order transitions.

## Step 6 — Complete buyer browsing, purchases, and reports

Complete public browsing and filters for category, price, location, and condition, with validation, pagination, and persistent filter selections. Product pages must clearly show current AI risk state, score where available, warning reasons, and the distinction between pending, failed, stale, and completed assessments.

Allow authenticated buyers to start seller conversations, place orders for available listings, view order history, submit fraud reports with notes and validated screenshot evidence, and track report status. Preserve transactional purchasing and revision/assessment snapshots, and prevent duplicate purchases or purchases of unavailable listings. Complete profile/contact updates with appropriate field validation and privacy boundaries.

Restrict conversations, order details, reports, and evidence to authorized participants and moderators. Buyers must never access admin data or modify risk rules. Verify browsing, filter edge cases, purchase races or duplicate submissions, report uploads, participant access, and profile editing.

## Step 7 — Expand administrator moderation and visibility

Complete the protected admin dashboard with total products, medium/high risk counts, and new fraud report counts. Provide searchable user and product information, including seller identity and buyer identity where an order exists, without fabricating a buyer for unsold products. Add risk-log filters by level, date range, and category, and show listing revisions, price anomalies, keyword flags, seller history, and model evidence actually recorded by the system.

Provide fraud report review with Pending, Under Review, Resolved, and Dismissed states, preserving existing history through explicit state mappings or migrations. Implement account blocking/unblocking, fraudulent listing removal, and account detail inspection with appropriately scoped private information. Audit every moderation action with admin identity, timestamp, target, reason, and relevant changes in the same transaction.

Allow administrator control over marketplace policy settings that have defined behavior. Keep administrator membership and security invariants protected. Treat 'open any account' as inspecting its information; do not add silent password bypasses or user impersonation. Verify admin-only access, report transitions, filter correctness, moderation effects, and audit completeness.

## Step 8 — Add unblock appeals and enforce restrictions

Implement an appeal workflow for blocked users, including sellers, to submit a reason and supporting evidence, view appeal status, and receive an admin decision. Provide a narrowly scoped authenticated route so blocked users can appeal while remaining unable to post products, chat, or perform other prohibited marketplace actions. Inspect the existing authentication behavior so account blocking does not accidentally make appeals inaccessible.

Add appeal tables/models, private evidence storage, validation, duplicate/open-appeal controls, review status, reviewer identity, timestamps, and decision notes as needed. Let the admin review evidence, approve or reject an appeal, and explicitly unblock the account when appropriate. Audit decisions and account status changes transactionally.

Enforce blocked-account restrictions in services and direct request handlers, including existing sessions, listing edits, uploads, chat sends, and purchase operations according to the documented policy. Define what happens to existing listings and outstanding orders without corrupting history. Verify evidence privacy, appeal access, decision transitions, and restriction enforcement.

## Step 9 — Implement AI settings, dataset export, and automatic retraining

Extend the existing versioned risk-rule and ML pipeline rather than creating a parallel pipeline. Let the admin edit supported thresholds with validation, explanations, versioning, and audit history. Export authorized fraud-training datasets as CSV with clear provenance, label definitions, appropriate privacy controls, and protection against spreadsheet formula injection.

Define which changes require rescoring and which actually require model retraining. When an AI-relevant admin change requires training, automatically enqueue a durable background training job. Threshold-only changes should apply the correct rules and trigger required rescans without unnecessary model fitting. Display queued/running/succeeded/failed training status and useful sanitized errors. Include job deduplication, retry policy, worker concurrency control, configuration/dataset snapshots, and audit linkage.

Use the real existing training pipeline and configured data sources. If sufficient labeled data or dependencies are unavailable, record an actionable failure instead of reporting successful training. Evaluate candidate models before activation, retain the working model when a candidate fails checks, and make any automatic activation policy explicit. Preserve reproducible artifacts, checksums, model history, and worker compatibility. Verify trigger behavior, failures, retries, evaluation gates, activation, rescans, and export authorization.

## Step 10 — Complete database migrations and deployment checks

Database changes needed by earlier features should be delivered with those features. In this step, reconcile and verify all resulting schema changes; do not defer required schema work until this step.

Inspect all new fields, tables, constraints, indexes, foreign keys, SQL functions/triggers, unmanaged models, and migration state. Ensure seller onboarding, appeals, moderation states, settings, and training jobs have the required persistence. Preserve immutable history and existing composite references. Add explicit least-privilege grants for new tables/functions to the correct web, worker, maintenance, or training process roles; do not grant blanket future-table access.

Verify both a fresh installation and an upgrade from the previous schema in disposable databases. Test backfills against representative existing records, migration ordering, concurrency-sensitive constraints, and model/migration state consistency. Before applying pending migrations to the configured working database, verify the target and arrange an appropriate recoverable backup without exposing credentials. Apply the necessary non-destructive migrations when the connection and privileges permit. Report precisely which migrations ran and which did not. Document any intentionally irreversible migration and its recovery procedure.

## Step 11 — Verify security, workflows, and responsive behavior

Run the relevant existing automated checks and add meaningful regression coverage for new behavior. Cover anonymous, buyer, seller, blocked, and sole-admin access; ownership and direct-request authorization; login/onboarding; listing uploads and revisions; scan-before-publication; private chat and evidence; transactional orders; reports; moderation audit logs; appeals; risk rules; CSV export; and background retraining failures and activation gates.

Run Django system checks, migration consistency checks, linting, appropriate unit/integration tests, and database privilege tests where available. Inspect the shared marketplace and admin workflows at representative mobile and desktop widths, including keyboard access, errors, empty states, and loading states. Use isolated test databases and synthetic test records rather than modifying real user data for testing.

Fix failures caused by the update, and report existing unrelated failures separately with evidence. Record actual commands, results, environment limitations, and acceptance gaps in `docs/PROJECT_UPDATE_VERIFICATION.md`. Do not claim checks passed if they were skipped or could not run.

## Step 12 — Update documentation and deliver the completed update

Update `README.md` and relevant setup, configuration, migration, worker, ML, and demo documentation to match the finished implementation. Document `/` and `/admin-app/`, buyer/seller onboarding, sole-admin provisioning, moderation, appeals, risk states, scan/publication policy, dataset export, training triggers, model activation policy, and required background processes. Include exact setup and upgrade commands without embedding credentials.

Update the Step 1 requirements checklist with implemented features, validation evidence, and any unresolved requirements. Ensure documentation distinguishes verified behavior from operational prerequisites and limitations, including synthetic model evaluation versus real-world accuracy. Check that links and commands match the actual files and management commands.

Deliver a concise completion report covering the user-visible changes, database migrations created and applied, tests actually run, required startup commands, and any remaining blockers. Preserve unrelated workspace changes and do not commit, push, or deploy unless separately requested.
