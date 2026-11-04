# Database Design

**Project:** Second-hand Marketplace & Product Fraud Risk Detection Database Application  
**Design baseline:** PostgreSQL 18; one database shared by Buyer, Seller and Admin applications  
**Prepared:** 3 November 2026  
**Requirements:** [PRD](PRD.md) and [system architecture](ARCHITECTURE.md)

This design separates editable marketplace state, immutable transaction evidence, human moderation decisions and AI predictions. It keeps core operational relations in third normal form (3NF), preserves the exact listing revision used by an order or investigation, and makes AI work durable when the worker is offline.

The SQL is a reference database implementation for the course. It is not a claim that the Django application, model training pipeline, media service or all acceptance tests are already implemented. Read [database setup and verification](database/README.md) for the executable scripts and measured validation status.

## 1. Deliverables

| Deliverable | Location |
| --- | --- |
| Entity relationships, cardinalities and diagram sources | [ER diagram](docs/database/ER_DIAGRAM.md) |
| Complete physical column definitions | [Data dictionary](docs/database/DATA_DICTIONARY.md) |
| Relations, keys and references | [Relational schema](docs/database/RELATIONAL_SCHEMA.md) |
| Core tables, keys, checks and indexes | [001_core.sql](database/001_core.sql) |
| AI, dataset and durable-job tables | [002_risk.sql](database/002_risk.sql) |
| Core transactional functions and validation triggers | [003_core_functions.sql](database/003_core_functions.sql) |
| AI worker functions, rescan support and risk views | [004_risk_functions.sql](database/004_risk_functions.sql) |
| Moderation/export, administrator queue and order-history views | [005_views.sql](database/005_views.sql) |
| Deterministic demonstration seed | [006_seed.sql](database/006_seed.sql) |
| Optional semantic review embeddings | [007_embeddings_optional.sql](database/007_embeddings_optional.sql) |
| Optional process-role privilege setup | [008_privileges.sql](database/008_privileges.sql) |

The SQL files are authoritative for exact column names, constraint names and function signatures. The dictionary and relational schema are derived from those definitions rather than from the earlier preliminary table count in the PRD.

The standard reference install defines **36 tables**: 23 shared identity/marketplace/infrastructure tables and 13 AI/provenance/recovery tables. The two P1 structures are present for future workflows; the optional vector script adds two P2 tables, making 38 physical relations in the complete dictionary. Additional join views do not duplicate stored entities.

## 2. Scope and modeling decisions

### 2.1 Shared identity and roles

One `users` relation stores each identity once. `auth_group` and `users_groups` represent buyer, seller and administrator memberships. A member can be both buyer and seller; an administrator identity stays separate from marketplace participation in the P0 workflow. Buyer and seller tables containing separate emails and passwords would introduce duplicate identities and conflicting account status.

Authentication infrastructure also includes content types, permissions, group-permission and user-permission junctions, and database-backed sessions. These relations appear in the physical ERD even though they are not marketplace domain entities. PostgreSQL process roles and Django user roles have different purposes: a pooled application connection does not identify the browser user automatically.

### 2.2 Product identity and immutable revisions

`products` stores stable identity and mutable workflow state: seller, current revision, availability, visibility and risk-context version. `product_revisions` stores the content of each immutable revision. Its primary key is `(product_id, revision_no)`.

The current-revision foreign key is `(products.product_id, products.current_revision_no) → product_revisions(product_id, revision_no)`. It is deferrable so a product and its initial revision can be created in one transaction. A draft may temporarily have no current revision; a published listing must have one.

Orders, reports, reviews, images and scan jobs reference both revision-key components. A report or order therefore continues to display the original terms after a later edit. `transactions` stores the purchase agreement and fulfilment state; it does not verify payment or hold funds.

Seller identity belongs to `products`, so an order does not store a second independently editable seller ID. Category identity belongs to a revision, preserving the category that applied at that point in time.

### 2.3 Availability and visibility are independent

Availability is `draft`, `available`, `reserved` or `sold`. Visibility is `visible`, `removed_by_seller` or `removed_by_admin`. Cancelling an order can release a reservation while leaving an administrator-hidden listing hidden. A single combined status would permit accidental restoration or require many ambiguous combinations.

### 2.4 Human decisions and AI output are different facts

`fraud_reports` records allegations and case workflow. `moderation_reviews` records evidence-backed human decisions. `risk_logs` records model output. A high-risk prediction is not a fraud verdict, a dismissed report is not a legitimate label, and no report is not evidence of legitimacy.

There is one append-only moderation chain per listing revision. A correction points to the immediate prior decision. One root per revision and one successor per decision prevent competing authoritative branches. Dataset export selects the effective latest decision first and then tests label eligibility. A latest `unresolved` decision removes the revision from an export even when an older decision was `fraud` or `legitimate`.

### 2.5 Historical names requested for AI support

| Requested name | Physical representation | Meaning |
| --- | --- | --- |
| `risk_score_history` | View joining canonical results with their jobs and pinned configuration | Every successful historical prediction; no second score table to synchronize |
| `fraud_logs` | View of high-risk predictions | AI screening alerts, explicitly separate from confirmed moderation verdicts |
| `review_embedding` | Optional P2 base table linked to a moderation review and embedding-model version | Semantic representation of review text for a later research extension |

`risk_logs` is the authoritative append-only prediction relation. The two views preserve the requested query names without introducing redundant copies of scores. Embeddings are outside the Random Forest P0 feature contract and require an optional `pgvector` installation; the core database does not depend on it.

### 2.6 Demonstration policy

The singleton `marketplace_settings` relation stores the configured currency, unanswered-order timeout and refresh timezone. The initial values are USD, 48 hours and `Asia/Shanghai`; they are demonstration settings, not assumptions about a participant's geography. Configure the currency before creating revisions. A database guard rejects a currency change once historical revision prices exist, and revision insertion must use that currency. Timeout and timezone remain controlled deployment policy.

## 3. Entity relationships and cardinality

The [ER diagrams](docs/database/ER_DIAGRAM.md) show the full physical model. Key relationship rules are:

| Relationship | Cardinality and rule |
| --- | --- |
| User to group | Many-to-many through a unique user/group membership |
| Seller to product | One seller owns zero or many products; every product has exactly one immutable seller |
| Product to revision | A draft may have zero revisions; a saved/published product has one or more; revision numbers are unique within that product |
| Product to current revision | Zero or one while a draft is constructed; exactly one after publication; target must belong to the same product |
| Revision to image | Zero to six images; each image association belongs to exactly one revision |
| Product and buyer to conversation | At most one conversation for that pair; the seller is derived from the product |
| Conversation to message | Zero or many messages; each message has exactly one sender who must be a participant |
| Product to order | Many historical cancelled orders; at most one order whose status is not `cancelled` |
| Buyer to order | One buyer can place many orders; an order has exactly one buyer |
| Order to status event | One initial event plus zero or more transition events |
| Revision to report | Zero or many reports; a report optionally references the reporter's order for that same revision |
| Report to attachment | Zero to three private evidence images |
| Revision to moderation decision | Zero or one chain; zero or many decisions in that chain |
| Decision to correction | Each decision has zero or one immediate successor and zero or one predecessor |
| Ruleset to rule | One ruleset contains versioned rule entries, unique by rule key |
| Revision to scan job | Zero or many jobs across content/context/configuration generations |
| Scan job to result | Zero or one result; a completed successful job has exactly one |
| Campaign to affected product | Many-to-many through campaign/product event receipts, with one receipt per pair |
| Dataset to record | One dataset contains many records with provenance and partition grouping |
| Model to evaluation | A model can have multiple measured evaluation slices |

Optional foreign keys mean a relationship can be absent; they do not allow dangling references. Mermaid diagrams simplify composite links visually; the SQL and relational schema retain every component.

## 4. Normalization to 3NF

### 4.1 Unnormalized starting point

A single spreadsheet might contain:

```text
ListingOrder(
  product_id, seller_email, seller_name, seller_roles[],
  revision_no, title, category_name, category_description, price,
  images[], buyer_email, order_id, order_status,
  messages[], reports[], report_attachments[],
  risk_scores[{model_version, thresholds, score, assessed_at}]
)
```

This stores repeating groups and unrelated facts together. An image or message has no stable key, changing a category description requires many updates, seller contact details can disagree between orders, and deleting an order can erase listing history.

### 4.2 First normal form

1NF requires scalar values in each operational column and identifiable rows. Move repeating images, messages, role memberships, attachments and predictions into child or junction relations. Each image becomes one `product_images` row; each membership becomes one `users_groups` row. Lists are not stored as comma-separated foreign keys.

```text
ProductRevisionFlat(product_id, revision_no, seller_id, seller_name,
                    title, category_id, category_name, category_description, price)
ProductImage(image_id, product_id, revision_no, sort_order, storage_key, ...)
```

The first relation now has atomic operational values, but still has partial and transitive dependencies.

### 4.3 Second normal form

2NF requires every non-key attribute to depend on the whole candidate key. In `ProductRevisionFlat`, `(product_id, revision_no)` identifies a revision, but `product_id → seller_id` depends on only part of that composite key. Move product-level ownership/workflow facts to `products`.

```text
products(product_id, seller_id, current_revision_no, availability, visibility, ...)
product_revisions(product_id, revision_no, title, category_id, price, ...)
```

Now title and price depend on the complete revision key. Neither `revision_no` alone nor `product_id` alone determines them. A separate revision key is meaningful even when two revisions happen to have identical prices.

### 4.4 Third normal form

3NF requires that for each nontrivial functional dependency `X → A`, `X` is a superkey or `A` is a prime attribute. Remove operational non-key determinants:

```text
product_id → seller_id → seller_name
category_id → category_name, category_description
group_id → group_name
model_id → version, artifact_checksum, feature_schema_id
dataset_id → dataset_version, export_cutoff, manifest_checksum
```

Seller attributes belong to `users`, category attributes to `categories`, group names to `auth_group`, model provenance to `risk_models`, and dataset metadata to `dataset_versions`. Relations refer to those facts by key.

An order retains `(product_id, revision_no)` rather than copying title, seller name and category description. The immutable referenced revision already preserves the purchased price and description. Risk results refer to a job; the job pins configuration, so model artifact paths and threshold values are not copied into every result.

### 4.5 Functional dependencies in the final design

| Relation family | Determinants and dependency rule |
| --- | --- |
| Users | `user_id → profile/status/credential fields`; normalized email is an alternate identifier |
| Role membership | `(user_id, group_id) → membership`; the unique pair prevents duplicate memberships |
| Categories | `category_id → name, description, is_active`; normalized category name is a candidate identifier |
| Marketplace settings | `singleton → currency, unanswered_order_timeout, refresh_timezone`; exactly one configured policy row |
| Products | `product_id → seller_id, current_revision_no, workflow/context fields` |
| Revisions | `(product_id, revision_no) → category_id, content, price, condition, location, created_at` |
| Images | `image_id → revision, storage metadata, position`; `(product_id, revision_no, sort_order)` is an alternate key |
| Conversations | `conversation_id → product_id, buyer_id, created_at`; `(product_id, buyer_id)` is an alternate key |
| Messages | `message_id → conversation_id, sender_id, text, times` |
| Orders | `transaction_id → buyer_id, revision, status, request identity, times`; `(buyer_id, request_key)` is an alternate key |
| Reports | `report_id → reporter, target revision, optional order, reason, case status, assignment, times` |
| Reviews | `review_id → target revision, reviewer, verdict/evidence, predecessor, decision time` |
| Rules | `(ruleset_id, rule_key) → rule content`; ruleset metadata remains in the parent relation |
| Jobs | `job_id → target/context, pinned configuration, state/lease/snapshot`; bound or unbound context tuples have conditional uniqueness |
| Results | `risk_id → job_id, prediction, explanation, time`; `job_id` is an alternate key |
| Campaign receipts | `(campaign_id, product_id) → processed work identity`; repeated delivery does not advance context again |
| Dataset records | `record_id → dataset/source/group, frozen inputs and label provenance`; group membership derives the split |
| Audit events | `audit_id → actor, typed target, reason, recorded change, occurred_at` |

Partial unique indexes express conditional business rules. For example, `product_id` is unique among non-cancelled orders; it is not a candidate key of the entire `transactions` relation because cancelled history remains.

### 4.6 Deliberate derived values and bounded snapshots

The operational model is normalized; the following persistence choices serve search, reproducibility or evidence:

| Value | Why it exists | Consistency rule |
| --- | --- | --- |
| Full-text expression index | Indexed search representation | PostgreSQL indexes `to_tsvector('simple', title || ' ' || description)` directly; no separately editable vector column |
| Text fingerprint | Versioned duplicate-text input | Created with the immutable revision using a documented normalization contract |
| Job feature snapshot | Exact values, missing indicators and reference facts used for inference | Written once under a live claim; retries reuse it |
| Dataset record features and label provenance | Frozen export used by a particular training experiment | Versioned immutable export; source identifiers remain relational |
| Model manifests/metrics and observed factors | Versioned structured technical evidence whose shape can change | Object/array shape checks plus application schema validation |
| Audit before/after objects | Record of a change at an earlier time | Append-only evidence; never used as the editable source of business state |
| Stored risk level | Historical classification under pinned thresholds | Completion function derives/checks the level using the job's ruleset |
| Declared feature-schema IDs on models/jobs | Artifact compatibility and frozen execution lineage | Model registration validates the dataset schema; bound jobs validate the model and ruleset schemas |
| Optional report/order and review/report target references | Enforce that contextual evidence concerns exactly the same revision and reporter | Composite foreign keys validate the repeated target components; targets are immutable |

JSON is not a shortcut for user, product, report or relationship tables. Atomic JSON documents are bounded technical artifacts with versioned semantics; their internal feature vectors are intentionally not claimed to be a fully decomposed relational model. Historical seller location in a feature snapshot is an observation at assessment time, different from the user's current profile location.

The model's declared feature schema can also be obtained through its dataset, and a bound job's schema can be obtained through its model. An order-linked report's target and reporter can also be obtained through its optional order; a report-linked decision can obtain its target through that report. These persisted declarations, plus `risk_level`, are controlled denormalization for execution lineage and the PRD's explicit composite target checks. They are not a claim of strict 3NF for every physical column. A strictly decomposed alternative would derive schema IDs through joins and move optional order/report associations into separate link relations, validating cross-target agreement transactionally. Canonical identity, listing content, conversation membership and order terms are normalized; historical snapshots and the listed target/technical declarations are the documented physical exceptions. This distinction matters when presenting the normalization proof in the course report.

## 5. Keys and integrity constraints

### 5.1 Primary and foreign keys

Domain entity identifiers use `bigint` identity columns; Django's content-type, permission and group references use its conventional integer identities. Revisions use the required composite primary key; dataset split groups use `(dataset_id, split_group_id)` and campaign receipts use `(campaign_id, product_id)`. Other junction relations have a surrogate identifier plus a unique relationship pair. Revision foreign keys always include `product_id` and `revision_no`.

Foreign keys retain referenced users, products, revisions, orders, decisions and registered configurations. Core historical relationships use `NO ACTION`/`RESTRICT`, rather than cascading a user deletion through orders and evidence. The exact action and deferrability of every foreign key appear in the [relational schema](docs/database/RELATIONAL_SCHEMA.md).

### 5.2 Important unique constraints

| Invariant | Unique constraint/index |
| --- | --- |
| One case-insensitive account per email | Unique index on `lower(email)` |
| No duplicate named category | Unique normalized category-name index |
| No duplicate role/permission links | Unique junction-key pairs |
| One image per revision position | Unique `(product_id, revision_no, sort_order)` |
| One product/buyer conversation | Unique `(product_id, buyer_id)` |
| One sale/reservation across concurrent buyers | Partial unique product index where order status is not `cancelled` |
| Idempotent order request | Unique `(buyer_id, request_key)`; fingerprint checked on reuse |
| One root moderation decision | Partial unique revision index where predecessor is null |
| One correction per predecessor | Unique non-null predecessor |
| One active model and ruleset | Separate partial unique activation indexes |
| One rule key in a ruleset | Unique `(ruleset_id, rule_key)` |
| Unbound scan deduplication | Unique revision/context where both configuration IDs are null |
| Bound scan deduplication | Unique revision/context/model/ruleset where both IDs are present |
| One prediction per job | Unique `risk_logs.job_id` |
| Campaign delivery deduplication | Unique source-event identity and campaign/product receipt |

### 5.3 Checks and validations

Money uses exact `numeric` values, with positive listing price and nonnegative optional original price. Timestamps use `timestamptz`; PostgreSQL represents an instant and the application chooses its display timezone. A currency code is stored with the immutable revision price and validated against `marketplace_settings` on insertion.

Checks constrain account, listing, order, report, job and review statuses; image size/type/position; message length; risk scores in `0..100`; nonnegative counters; both-null-or-both-bound job configuration; and coherent lifecycle timestamps. Cross-table and state-transition rules use foreign keys, triggers or transactional functions because an ordinary `CHECK` cannot safely validate other rows.

The database validates image metadata and maximum association counts. Pillow must still decode the bytes and verify actual format/dimensions. A filename or claimed MIME type alone cannot perform that validation.

## 6. Transactions and concurrency

### 6.1 Publication

1. Authenticate the seller, validate uploads and store new immutable files.
2. Begin a database transaction; lock affected account rows in ID order and then the product.
3. Verify ownership, active status and absence of an active/completed sale that prohibits editing.
4. Allocate a new revision number; insert its content and image associations.
5. Advance the current revision and publish as applicable.
6. A local database trigger queues the assessment before commit. No Python inference or network request runs inside a trigger.

The same transaction owns the revision, images, pointer and queued job. A queue insert failure rolls publication back. Database and filesystem writes are not one transaction: failed publication may leave unreferenced new files, which a controlled reference-aware cleanup handles later.

### 6.2 Orders

Resolve a matching `(buyer_id, request_key)` replay before creating work, including after waiting for locks. Compare its stored request fingerprint; a reused key with different request data is a conflict.

For new work, lock users in ID order and then the product; verify current revision, visible/available state, active participants and no self-purchase. Create the `placed` order and initial event and reserve the product atomically. The partial unique index remains the final protection when two buyers race.

Transitions take the product lock before the order lock, validate state and actor, append history and update availability in the same transaction. Completion marks sold; cancellation releases the reservation. Both preserve visibility. Repeating an already-applied action must not append another event. Only unanswered `placed` orders are eligible for scheduled expiry; `marketplace_settings.unanswered_order_timeout` initially sets this to 48 hours.

### 6.3 Moderation and administrative audit

Lock the product before appending a decision, verify the expected chain head, then insert the decision, mandatory audit and any seller-history rescan obligation in the same transaction. Account moderation locks affected users first. Typed audit foreign keys identify the actual target, including an order for dispute resolution.

An audit insert failure must fail the associated privileged action. Actor/reason validation is meaningful only when the backend derives the actor from an authenticated session. A database argument or session setting containing a user ID is not authentication by itself.

### 6.4 Worker leases and recovery

Claim short-lived work with `FOR UPDATE SKIP LOCKED`, pin compatible model/ruleset versions and assign a new claim token. Persist a consistent feature snapshot before inference, then release claim-transaction locks while the model runs.

Snapshot, heartbeat, failure and completion calls check `processing` state, current token and unexpired lease using a live database clock. A worker returning after its claim expired cannot overwrite another worker's work. Completion locks the job, creates one result and marks the job successful atomically. Bounded attempts and retry times distinguish temporary failure from permanent failure.

Model/rule changes immediately make old scores stale through read-time matching. Recoverable campaigns advance contexts for eligible listings in bounded batches. A unique campaign/product receipt makes the batch idempotent even after a crash; daily campaigns freeze their cutoff and timezone-derived event date.

### 6.5 Lock order

For operations involving marketplace accounts and content: affected `users` rows in ascending ID order → `products` → order/review rows. Configuration changes use the shared configuration advisory lock before model/ruleset rows. Job finalization locks jobs and does not acquire product locks afterward. Campaign batches follow the product-before-job path. Retry a deadlocked transaction as a bounded whole operation with its original idempotency identity.

## 7. AI data, history and training provenance

### 7.1 Version identities

`feature_schemas` freezes the feature extraction contract: names, windows, keyword/normalization rules, missing-data treatment and version. `dataset_versions` identifies a frozen export/generator manifest. Dataset sources record origin and license/access notes; split groups keep related sellers/templates/duplicates in one partition. Dataset records retain source, group, feature time, synthetic flag, label origin and optional product/review lineage.

`risk_models` registers a trusted fitted pipeline with immutable artifact path/checksum, feature schema, dataset, seed, dependency/class mapping metadata and registration provenance. Evaluation rows record measured partitions/slices and sample counts. A ruleset changes display thresholds and operating rules; a feature-schema change requires a compatible retrained model.

Dataset partition is derived from the record's split group. It is not independently editable in both rows. Grouping must be established before fitting; the database stores the grouping contract and manifest while the export pipeline verifies seller/template/duplicate membership and temporal leakage.

### 7.2 Point-in-time features

The exact versioned windows, normalization, reference selection, predictor order and missing-value semantics are frozen in [FEATURE_CONTRACT.md](docs/FEATURE_CONTRACT.md). Register that complete definition as `marketplace-v1`; a contract change requires a new immutable schema version and compatible retraining. [CONFIGURATION.md](docs/CONFIGURATION.md) resolves currency/language/location defaults, request limits, rate limits, retention and restricted-account access. SQL metadata constraints are already present; application enforcement and feature calculation require their own verification.

The P0 feature snapshot contains price ratio and comparable count/missing flag, keyword count, seller age, prior confirmed fraud count, seven-day posting frequency, image count, location difference/missing flags and prior same-seller duplicate-text count.

Feature extraction uses facts known by `feature_as_of`, excludes the target from seller fraud and comparable-price counts, and resolves historical decision chains as known at that time. For a comparable product, use one eligible revision as of the cutoff rather than counting every edit as another product. Freeze the baseline selection policy in the feature schema. Preserve the seller location and baseline reference values actually used.

Private messages, passwords, contact details, evidence images, prior AI scores and the target's final verdict do not become P0 predictor columns. Export labels may be decided after feature time; they must never leak back into the point-in-time predictors.

### 7.3 Current-risk semantics

A result is current only when its revision/context match the product, its model/ruleset match current active configuration, its feature schema matches the model, its job succeeded, and the snapshot is within maximum age, initially 24 hours.

| State | Meaning | Numeric risk shown as current? |
| --- | --- | --- |
| `ready` | A valid current result exists | Yes |
| `scanning` | Current work has a live processing lease | No |
| `pending` | Current queued/unbound/retry/recovery work exists, or first assessment is missing | No |
| `failed` | Current work failed permanently with no runnable replacement | No |
| `stale` | Historical predictions exist but none is current and no current work is runnable | No |

The low-risk filter requires `ready` and the low-risk classification. Missing, stale and failed assessments never default to zero. Older results remain queryable through `risk_score_history` with their pinned context/configuration.

### 7.4 Review embeddings

The optional extension stores embeddings separately from review evidence and Random Forest features. Each vector references the immutable review and exact embedding-model metadata. Vector dimensions, model version and source-content fingerprint prevent mixing incompatible representations. Semantic similarity does not produce a confirmed fraud label or override the canonical moderation chain.

## 8. Index and query design

| Access path | Planned index/strategy |
| --- | --- |
| Current public catalog | Product availability/visibility/time plus current-revision join |
| Title/description search | GIN over the `to_tsvector('simple', title || ' ' || description)` expression; explicit configuration avoids assuming an approved listing language |
| Category/condition/price filters | Revision B-tree filter indexes; current pointer removes old revisions from results |
| Seller listing history | Product seller/time/ID; revision/product and publication-time paths |
| Buyer order history | Buyer/time/ID and product/order paths |
| Conversation polling | Conversation ID plus increasing message ID/time cursor |
| Report queue | Status/assignment/time indexes and revision target lookup |
| Decision head lookup | Revision/time plus root/successor uniqueness |
| Claim runnable work | Partial queued retry-time index and processing lease-expiry index |
| Current risk | Bound context uniqueness and unique result/job join |
| Campaign batches | Campaign status/cursor and campaign/product receipt key |
| Expired sessions | Session expiry index for controlled cleanup |

Views such as `current_listing_risk`, `admin_review_queue` and `seller_order_history` centralize joins. They do not impose browser-user ownership automatically. Queries must still filter to authorized principals. Use cursor pagination with a stable ID tiebreaker rather than relying on a nonunique timestamp alone.

Run the representative `EXPLAIN (ANALYZE, BUFFERS)` queries after loading a measured course-scale dataset. Record row counts, PostgreSQL version and hardware. An index's existence is not evidence that a specific performance target has been reached; no benchmark result is invented in this design.

## 9. Retention, privacy and database privileges

Users and listings are deactivated/removed softly. Orders, revisions, referenced images, moderation decisions, predictions and audits remain linked. Ordinary application code cannot overwrite immutable history. Correct a decision by appending a successor, a listing by creating a revision, and a model artifact by registering a new version.

File storage keys identify generated immutable objects. Public listing images and private report evidence use different serving paths; evidence is returned only after reporter/administrator authorization. SQL cannot ensure external bytes have not been overwritten, so storage permissions, checksums, application rules and coordinated backups complete the contract.

Separate migration/owner, web runtime and worker credentials. Runtime roles receive only the required table/function permissions and no history-update/delete or schema-owner privileges. Worker mutation APIs validate leases; raw job/result writes must not be granted to the worker. Database object privileges constrain processes, while Django enforces per-user read authorization and CSRF protection.

Sessions are disposable operational infrastructure and can expire independently of historical business evidence. Shared login/message/listing/report throttling remains application implementation work. Keep session tokens, raw chat and passwords out of audit payloads and dataset manifests. Before collecting real evidence, approve an actual retention policy and a controlled anonymization/erasure process that preserves required relational integrity.

Back up PostgreSQL and referenced media/model artifacts as one recovery set. A restore drill must verify an order's historical revision, private attachment accessibility, decision chain, model checksum and result/job references.

## 10. Django mapping and migration ownership

Create the custom email-login user before the first Django migration and map its database table/columns deliberately. Use Django password APIs and the configured bcrypt-backed hasher; SQL does not implement password hashing. Marketplace blocking must remain distinct from disabling all authentication so blocked members can view history and fulfil existing obligations.

Django 5.2 has composite primary-key support but an ordinary `ForeignKey` cannot target a composite primary key. Preserve explicit `product_id`/`revision_no` components and add the composite foreign keys and deferrable current pointer through reviewed SQL migrations. Query helpers must join both fields. Do not rely on an internal ORM relationship helper to create database constraints.

The standalone DDL includes a physical reference for Django infrastructure. Do not run independent Django `CREATE TABLE` migrations over an already bootstrapped copy. Choose one migration authority: translate the reference into initial Django migrations with state/database operations kept consistent, or deliberately adopt an existing schema after verifying the migration state. This repository has not silently marked future Django migrations as applied.

## 11. Verification and remaining application work

The reference SQL supports database-level constraint and workflow checks. [Setup instructions](database/README.md) record how to build a disposable database and what was actually tested. Appropriate integration scenarios include:

1. Duplicate case-insensitive emails and duplicate membership pairs fail.
2. Cross-product revision pointers and mismatched report/order revisions fail.
3. Invalid prices, image counts, statuses, risk scores and half-bound jobs fail.
4. Two competing buyers produce one non-cancelled order; replayed keys preserve the original request result.
5. Invalid order transitions fail and valid transitions create history without restoring hidden visibility.
6. Competing moderation corrections cannot branch; unresolved corrections remove previous export eligibility.
7. Publication queues a durable job while the worker is stopped.
8. Old worker claims cannot write after lease replacement; repeated completion leaves one prediction.
9. Changed revision/context/configuration and expired snapshot age prevent a current low-risk badge.
10. Privileged changes and required audits commit or roll back together.

Still required in the application are authenticated actor derivation, object-scoped reads, CSRF/session setup, actual file decoding and storage, shared rate-limit invocation, trusted model loading and feature extraction, offline training/evaluation, campaign scheduling, backup restoration and full concurrent/browser acceptance tests. The database design makes these responsibilities explicit without presenting them as completed features.

## 12. Technical references

The implementation uses PostgreSQL constraints, partial indexes, row locks and views. Exact version behavior should be checked against the [PostgreSQL 18 CREATE TABLE documentation](https://www.postgresql.org/docs/18/sql-createtable.html), [CREATE INDEX documentation](https://www.postgresql.org/docs/18/sql-createindex.html), [locking documentation](https://www.postgresql.org/docs/18/explicit-locking.html), and [Django 5.2 composite-primary-key guidance](https://docs.djangoproject.com/en/5.2/topics/composite-primary-key/).
