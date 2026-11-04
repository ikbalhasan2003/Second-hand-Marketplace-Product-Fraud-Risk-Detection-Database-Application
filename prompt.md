# Implementation prompts

Use these prompts one at a time, in order. Paste the shared instruction before each task prompt.

## Shared instruction

```text
Work in D:\SecondHandFraudDB.

Read applicable AGENTS.md instructions and relevant sections of PRD.md,
ARCHITECTURE.md, TECH_STACK.md, DATABASE_DESIGN.md, database/README.md,
and docs/UI_WIREFRAME_SPEC.md. Inspect the existing implementation first.

Preserve unrelated changes. Reuse existing database functions, constraints,
immutable revisions and audit mechanisms. Keep the work within P0 scope.

Implement the requested functionality, add appropriate focused tests, and
update setup documentation. Never fabricate model artifacts, evaluation
metrics or test results.

Finish by reporting changed files, checks actually executed, and any
remaining gaps or blockers.
```

## 1. Finalize configuration and implementation decisions

```text
Resolve the remaining configuration decisions for this project.

Define configurable defaults for currency, supported language, demo
locations, upload limits, rate limits, evidence retention, and
deactivated-account access. Finalize the versioned feature contract,
including temporal windows, text normalization, comparable-price
selection and missing-value handling.

Document assumptions and keep the PRD, architecture and database design
consistent. Distinguish implemented behavior from proposed behavior.
```

## 2. Set up the Django project

```text
Create the runnable Django foundation using the version families specified
in TECH_STACK.md. Verify compatibility and pin exact dependencies.

Add manage.py, settings, root URLs, WSGI/ASGI configuration, environment
configuration, logging, static/media configuration and separate Buyer,
Seller and Admin application entry points.

Define the custom email-login user and its database mapping before the
first migration. Coordinate schema creation with the existing SQL design.

Provide reproducible Windows setup instructions and run relevant Django
configuration checks.
```

## 3. Integrate the existing PostgreSQL schema

```text
Integrate the reference PostgreSQL schema with Django using one documented
migration authority.

Implement coordinated migration state and database operations. Preserve
composite revision references, immutable history, triggers, partial
indexes, views, transactional functions and process privileges.

Avoid duplicate table creation or blindly marking migrations as applied.
Keep optional pgvector outside the required baseline.

Verify installation into a fresh disposable database and run the existing
database regression and privilege checks. Document the migration strategy.
```

## 4. Implement accounts and authorization

```text
Implement registration, login, logout, password changes and session
invalidation using Django password APIs and the configured bcrypt hasher.

Use one identity with explicit buyer/seller memberships and separately
provisioned administrator accounts. Support authenticated role enabling
without granting roles through login or app switching.

Enforce account status, role and object ownership on every protected
request. Configure CSRF protection and preserve blocked members' permitted
history and existing-order workflows.

Test duplicate emails, role escalation, cross-app access and unrelated
object access.
```

## 5. Build the Seller App

```text
Implement the Seller App's functional pages and backend integration:
dashboard, listing creation/editing, revision history, sales management
and existing buyer conversations.

Support validated image uploads, draft saves, atomic publication,
immutable revisions and durable scan enqueueing. Preserve separate
availability and visibility states.

Prevent unauthorized edits and material changes during active orders or
after completed sales. Implement authorized fulfilment, cancellation and
dispute actions through shared services.

Follow the wireframe specification and test publication, revision conflicts
and ownership restrictions.
```

## 6. Build the Buyer App and shared marketplace workflows

```text
Implement public browsing, PostgreSQL full-text search, filters,
pagination, listing details, purchases, conversations and fraud reports.

Connect orders to the existing transactional database functions. Preserve
idempotency, immutable purchase revisions and concurrent purchase
protection. Implement shared polling chat with participant-only access
and recipient-only read receipts.

Implement private report attachments and reporter status pages. Display
server-derived risk states; only current completed assessments qualify
for the Low-risk filter.

Test ownership, competing orders, chat privacy and private evidence access.
```

## 7. Build the dataset and model pipeline

```text
Implement the reproducible dataset generation/export, training and
evaluation pipeline under ml/.

Record provenance, synthetic flags, feature timestamps, schema versions,
label sources and immutable manifests. Prevent future-evidence leakage
and related-record leakage across evaluation partitions.

Train a saved preprocessing-plus-Random-Forest pipeline. Compare it with
rules and Logistic Regression on identical partitions. Report precision,
recall, F1, average precision and confusion matrices, separating synthetic
and real sources where available.

Register checksums, dependencies, seeds, class mappings and limitations.
Synthetic-only results must be identified clearly.
```

## 8. Implement the risk worker and scheduling

```text
Implement versioned feature extraction, trusted model loading and risk
inference using the existing PostgreSQL job and campaign functions.

Support job claiming, lease renewal, fencing tokens, retry/backoff,
expired-lease recovery and idempotent result completion. Prevent outdated
workers or assessment contexts from publishing current results.

Implement recoverable rescan campaigns, freshness maintenance and
unanswered-order expiry commands with documented scheduling.

Verify stopped-worker recovery, duplicate execution, configuration changes,
expired snapshots and explicit pending/failed/stale risk states.
```

## 9. Build the Admin App

```text
Implement the Admin dashboard, deduplicated moderation queue, case
workspace, dispute resolution, audit browser, model/rules management
and administrator-only dataset exports.

Preserve private evidence permissions and append-only canonical decision
chains. A newer unresolved decision must exclude an older training label.

Make privileged mutations and their required audit events atomic. Validate
compatible model/ruleset activation and schedule recoverable rescans.

Never block accounts or remove listings solely because of an AI score.
Test administrator authorization, concurrent corrections and audit failure
rollback.
```

## 10. Complete the interface

```text
Complete and integrate all 17 pages in docs/UI_WIREFRAME_SPEC.md using
Django templates, local Bootstrap assets and small JavaScript modules.

Reuse shared navigation, forms, listing cards, risk panels, order
timelines, conversation components and audit receipts.

Implement loading, empty, validation, forbidden, conflict, failed and
restricted states. Preserve drafts, focus and scroll during polling.

Verify responsive layouts, keyboard access, labels and accessible feedback.
Render actual backend state without fabricated counts, scores or progress.
```

## 11. Verify and prepare delivery

```text
Assess the completed application against PRD acceptance criteria AC-01
through AC-23, reusing existing database evidence where applicable.

Run PostgreSQL-backed application, permission, concurrency, worker recovery,
upload and model reproducibility checks. Measure the documented search
and scan performance targets using realistic workloads.

Perform a coordinated database/media/artifact restore drill in an isolated
target. Record actual results and resolve discovered defects.

Complete local startup instructions, configuration documentation, the
Buyer/Seller/Admin demonstration script and final academic report.
Clearly identify any acceptance criteria that remain unmet.
```
