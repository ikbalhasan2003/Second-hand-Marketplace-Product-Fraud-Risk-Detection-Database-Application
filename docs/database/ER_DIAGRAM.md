# Entity–Relationship Diagrams

These diagrams map the physical PostgreSQL schema. They are split for readable assessment and printing; together they cover every base table, including Django infrastructure and optional extensions. Exact composite foreign keys, conditional uniqueness and checks are listed in the [relational schema](RELATIONAL_SCHEMA.md) and [data dictionary](DATA_DICTIONARY.md).

**Legend:** `||` exactly one; `o|` zero or one; `o{` zero or many. The parent-side optional marker follows nullable foreign keys. A diagram showing zero children means a parent may exist before children are inserted; lifecycle checks can require a child later. PK/FK labels identify key columns. The deferrable product/current-revision relationship forms a deliberate cycle with product/revision ownership.

A high-risk AI prediction is an observation. Confirmed fraud/legitimacy comes only from the moderation decision chain. `fraud_logs` and `risk_score_history` are views, so they do not appear as duplicate entities.

## Identity, Django infrastructure and deployment settings

[Download Mermaid source](../diagrams/database-identity.mmd)

```mermaid
erDiagram
    users {
        bigint user_id PK
        varchar email
        varchar status
    }
    auth_group {
        integer id PK
    }
    users_groups {
        bigint id PK
        bigint user_id FK
        integer group_id FK
    }
    django_content_type {
        integer id PK
    }
    auth_permission {
        integer id PK
        integer content_type_id FK
    }
    auth_group_permissions {
        bigint id PK
        integer group_id FK
        integer permission_id FK
    }
    users_user_permissions {
        bigint id PK
        bigint user_id FK
        integer permission_id FK
    }
    django_session {
        varchar session_key PK
    }
    marketplace_settings {
        boolean singleton PK
    }
    users ||--o{ users_groups : "user_id"
    auth_group ||--o{ users_groups : "group_id"
    django_content_type ||--o{ auth_permission : "content_type_id"
    auth_group ||--o{ auth_group_permissions : "group_id"
    auth_permission ||--o{ auth_group_permissions : "permission_id"
    users ||--o{ users_user_permissions : "user_id"
    auth_permission ||--o{ users_user_permissions : "permission_id"
```

## Listings, messaging and orders

[Download Mermaid source](../diagrams/database-marketplace.mmd)

```mermaid
erDiagram
    users {
        bigint user_id PK
        varchar email
        varchar status
    }
    categories {
        bigint category_id PK
    }
    products {
        bigint product_id PK, FK
        bigint seller_id FK
        integer current_revision_no FK
        bigint context_version
    }
    product_revisions {
        bigint product_id PK, FK
        integer revision_no PK
        bigint category_id FK
        varchar title
    }
    product_images {
        bigint image_id PK
        bigint product_id FK
        integer revision_no FK
    }
    conversations {
        bigint conversation_id PK
        bigint product_id FK
        bigint buyer_id FK
    }
    chat_messages {
        bigint message_id PK
        bigint conversation_id FK
        bigint sender_id FK
    }
    transactions {
        bigint transaction_id PK
        bigint product_id FK
        integer revision_no FK
        bigint buyer_id FK
        varchar status
    }
    order_status_history {
        bigint event_id PK
        bigint transaction_id FK
        bigint actor_id FK
    }
    users ||--o{ products : "seller_id"
    product_revisions o|--o| products : "product_id_current_revision_no"
    products ||--o{ product_revisions : "product_id"
    categories ||--o{ product_revisions : "category_id"
    product_revisions ||--o{ product_images : "product_id_revision_no"
    products ||--o{ conversations : "product_id"
    users ||--o{ conversations : "buyer_id"
    conversations ||--o{ chat_messages : "conversation_id"
    users ||--o{ chat_messages : "sender_id"
    users ||--o{ transactions : "buyer_id"
    product_revisions ||--o{ transactions : "product_id_revision_no"
    transactions ||--o{ order_status_history : "transaction_id"
    users o|--o{ order_status_history : "actor_id"
```

## Reports, moderation, audit and P1 extensions

[Download Mermaid source](../diagrams/database-moderation.mmd)

```mermaid
erDiagram
    users {
        bigint user_id PK
        varchar email
        varchar status
    }
    products {
        bigint product_id PK, FK
        bigint seller_id FK
        integer current_revision_no FK
        bigint context_version
    }
    product_revisions {
        bigint product_id PK, FK
        integer revision_no PK
        bigint category_id FK
        varchar title
    }
    transactions {
        bigint transaction_id PK
        bigint product_id FK
        integer revision_no FK
        bigint buyer_id FK
        varchar status
    }
    fraud_reports {
        bigint report_id PK
        bigint product_id FK
        integer revision_no FK
        bigint reporter_id FK
        bigint transaction_id FK
        varchar status
        bigint assigned_admin_id FK
    }
    report_attachments {
        bigint attachment_id PK
        bigint report_id FK
    }
    moderation_reviews {
        bigint review_id PK
        bigint product_id FK
        integer revision_no FK
        bigint report_id FK
        bigint reviewer_id FK
        bigint supersedes_review_id FK
    }
    admin_audit_logs {
        bigint audit_id PK
        bigint admin_id FK
        bigint user_id FK
        bigint product_id FK
        bigint report_id FK
        bigint review_id FK
        bigint transaction_id FK
        bigint model_id FK
        bigint ruleset_id FK
        bigint dataset_id FK
    }
    seller_appeals {
        bigint appeal_id PK
        bigint review_id FK
        bigint seller_id FK
        varchar status
        bigint assigned_admin_id FK
    }
    notifications {
        bigint notification_id PK
        bigint recipient_id FK
        varchar source_event_key
        bigint product_id FK
        bigint transaction_id FK
        bigint report_id FK
    }
    users ||--o{ products : "seller_id"
    product_revisions o|--o| products : "product_id_current_revision_no"
    products ||--o{ product_revisions : "product_id"
    users ||--o{ transactions : "buyer_id"
    product_revisions ||--o{ transactions : "product_id_revision_no"
    users ||--o{ fraud_reports : "reporter_id"
    users o|--o{ fraud_reports : "assigned_admin_id"
    product_revisions ||--o{ fraud_reports : "product_id_revision_no"
    transactions o|--o{ fraud_reports : "transaction_id_product_id_revision_no_reporter_id"
    fraud_reports ||--o{ report_attachments : "report_id"
    users ||--o{ moderation_reviews : "reviewer_id"
    product_revisions ||--o{ moderation_reviews : "product_id_revision_no"
    fraud_reports o|--o{ moderation_reviews : "report_id_product_id_revision_no"
    moderation_reviews o|--o| moderation_reviews : "supersedes_review_id_product_id_revision_no"
    users ||--o{ admin_audit_logs : "admin_id"
    users o|--o{ admin_audit_logs : "user_id"
    products o|--o{ admin_audit_logs : "product_id"
    fraud_reports o|--o{ admin_audit_logs : "report_id"
    moderation_reviews o|--o{ admin_audit_logs : "review_id"
    transactions o|--o{ admin_audit_logs : "transaction_id"
    moderation_reviews ||--o{ seller_appeals : "review_id"
    users ||--o{ seller_appeals : "seller_id"
    users o|--o{ seller_appeals : "assigned_admin_id"
    users ||--o{ notifications : "recipient_id"
    products o|--o{ notifications : "product_id"
    transactions o|--o{ notifications : "transaction_id"
    fraud_reports o|--o{ notifications : "report_id"
```

## AI datasets, grouping, model provenance and evaluation

[Download Mermaid source](../diagrams/database-ai-provenance.mmd)

```mermaid
erDiagram
    users {
        bigint user_id PK
        varchar email
        varchar status
    }
    product_revisions {
        bigint product_id PK, FK
        integer revision_no PK
        bigint category_id FK
        varchar title
    }
    moderation_reviews {
        bigint review_id PK
        bigint product_id FK
        integer revision_no FK
        bigint report_id FK
        bigint reviewer_id FK
        bigint supersedes_review_id FK
    }
    admin_audit_logs {
        bigint audit_id PK
        bigint admin_id FK
        bigint user_id FK
        bigint product_id FK
        bigint report_id FK
        bigint review_id FK
        bigint transaction_id FK
        bigint model_id FK
        bigint ruleset_id FK
        bigint dataset_id FK
    }
    feature_schemas {
        bigint feature_schema_id PK
        varchar version
    }
    dataset_sources {
        bigint source_id PK
    }
    dataset_versions {
        bigint dataset_id PK
        varchar version
        bigint feature_schema_id FK
        varchar state
        bigint created_by FK
    }
    dataset_split_groups {
        bigint split_group_id PK
        bigint dataset_id PK, FK
        varchar partition
    }
    dataset_records {
        bigint record_id PK
        bigint dataset_id FK
        bigint source_id FK
        bigint split_group_id FK
        bigint product_id FK
        integer revision_no FK
        bigint review_id FK
    }
    risk_models {
        bigint model_id PK
        varchar version
        bigint feature_schema_id FK
        bigint dataset_id FK
        varchar state
        bigint registered_by FK
    }
    model_evaluations {
        bigint evaluation_id PK
        bigint model_id FK
        varchar partition
    }
    users ||--o{ moderation_reviews : "reviewer_id"
    product_revisions ||--o{ moderation_reviews : "product_id_revision_no"
    moderation_reviews o|--o| moderation_reviews : "supersedes_review_id_product_id_revision_no"
    users ||--o{ admin_audit_logs : "admin_id"
    users o|--o{ admin_audit_logs : "user_id"
    moderation_reviews o|--o{ admin_audit_logs : "review_id"
    risk_models o|--o{ admin_audit_logs : "model_id"
    dataset_versions o|--o{ admin_audit_logs : "dataset_id"
    feature_schemas ||--o{ dataset_versions : "feature_schema_id"
    users ||--o{ dataset_versions : "created_by"
    dataset_versions ||--o{ dataset_split_groups : "dataset_id"
    dataset_versions ||--o{ dataset_records : "dataset_id"
    dataset_sources ||--o{ dataset_records : "source_id"
    moderation_reviews o|--o{ dataset_records : "review_id"
    dataset_split_groups ||--o{ dataset_records : "dataset_id_split_group_id"
    product_revisions o|--o{ dataset_records : "product_id_revision_no"
    feature_schemas ||--o{ risk_models : "feature_schema_id"
    dataset_versions ||--o{ risk_models : "dataset_id"
    users ||--o{ risk_models : "registered_by"
    risk_models ||--o{ model_evaluations : "model_id"
```

## AI execution, versioned rules and rescan recovery

[Download Mermaid source](../diagrams/database-ai-execution.mmd)

```mermaid
erDiagram
    users {
        bigint user_id PK
        varchar email
        varchar status
    }
    products {
        bigint product_id PK, FK
        bigint seller_id FK
        integer current_revision_no FK
        bigint context_version
    }
    product_revisions {
        bigint product_id PK, FK
        integer revision_no PK
        bigint category_id FK
        varchar title
    }
    admin_audit_logs {
        bigint audit_id PK
        bigint admin_id FK
        bigint user_id FK
        bigint product_id FK
        bigint report_id FK
        bigint review_id FK
        bigint transaction_id FK
        bigint model_id FK
        bigint ruleset_id FK
        bigint dataset_id FK
    }
    feature_schemas {
        bigint feature_schema_id PK
        varchar version
    }
    risk_models {
        bigint model_id PK
        varchar version
        bigint feature_schema_id FK
        bigint dataset_id FK
        varchar state
        bigint registered_by FK
    }
    risk_rulesets {
        bigint ruleset_id PK
        varchar version
        bigint feature_schema_id FK
        varchar state
        bigint created_by FK
        bigint published_by FK
    }
    risk_rules {
        bigint rule_id PK
        bigint ruleset_id FK
    }
    risk_scan_jobs {
        bigint job_id PK
        bigint product_id FK
        integer revision_no FK
        bigint context_version
        bigint model_id FK
        bigint ruleset_id FK
        bigint feature_schema_id FK
        varchar source_event_key
        varchar status
        uuid claim_token
    }
    risk_logs {
        bigint risk_id PK
        bigint job_id FK
        smallint risk_score
    }
    risk_rescan_campaigns {
        bigint campaign_id PK
        varchar source_event_key
        bigint source_audit_id FK
        bigint seller_id FK
        bigint target_product_id FK
        varchar status
    }
    risk_rescan_events {
        bigint campaign_id PK, FK
        bigint product_id PK, FK
        bigint job_id FK
    }
    users ||--o{ products : "seller_id"
    product_revisions o|--o| products : "product_id_current_revision_no"
    products ||--o{ product_revisions : "product_id"
    users ||--o{ admin_audit_logs : "admin_id"
    users o|--o{ admin_audit_logs : "user_id"
    products o|--o{ admin_audit_logs : "product_id"
    risk_models o|--o{ admin_audit_logs : "model_id"
    risk_rulesets o|--o{ admin_audit_logs : "ruleset_id"
    feature_schemas ||--o{ risk_models : "feature_schema_id"
    users ||--o{ risk_models : "registered_by"
    feature_schemas ||--o{ risk_rulesets : "feature_schema_id"
    users ||--o{ risk_rulesets : "created_by"
    users o|--o{ risk_rulesets : "published_by"
    risk_rulesets ||--o{ risk_rules : "ruleset_id"
    risk_models o|--o{ risk_scan_jobs : "model_id"
    risk_rulesets o|--o{ risk_scan_jobs : "ruleset_id"
    feature_schemas o|--o{ risk_scan_jobs : "feature_schema_id"
    product_revisions ||--o{ risk_scan_jobs : "product_id_revision_no"
    risk_scan_jobs ||--o| risk_logs : "job_id"
    admin_audit_logs o|--o| risk_rescan_campaigns : "source_audit_id"
    users o|--o{ risk_rescan_campaigns : "seller_id"
    products o|--o{ risk_rescan_campaigns : "target_product_id"
    risk_rescan_campaigns ||--o{ risk_rescan_events : "campaign_id"
    products ||--o{ risk_rescan_events : "product_id"
    risk_scan_jobs ||--o{ risk_rescan_events : "job_id"
```

## Optional P2 review embeddings

[Download Mermaid source](../diagrams/database-embeddings.mmd)

```mermaid
erDiagram
    users {
        bigint user_id PK
        varchar email
        varchar status
    }
    moderation_reviews {
        bigint review_id PK
        bigint product_id FK
        integer revision_no FK
        bigint report_id FK
        bigint reviewer_id FK
        bigint supersedes_review_id FK
    }
    embedding_models {
        bigint embedding_model_id PK
        varchar version
        bigint registered_by FK
    }
    review_embedding {
        bigint review_embedding_id PK
        bigint review_id FK
        bigint embedding_model_id FK
    }
    users ||--o{ moderation_reviews : "reviewer_id"
    moderation_reviews o|--o| moderation_reviews : "supersedes_review_id_product_id_revision_no"
    users ||--o{ embedding_models : "registered_by"
    moderation_reviews ||--o{ review_embedding : "review_id"
    embedding_models ||--o{ review_embedding : "embedding_model_id"
```

## Cardinality refinements

- `products → product_revisions`: a draft can exist without a revision; publication requires a valid current revision. Both product ID and revision number participate in every historical link.
- `transactions`: the product can have several cancelled orders, but a partial unique index permits at most one non-cancelled order, including a completed sale.
- `product_images` and `report_attachments`: bounded unique positions enforce at most six listing images and three private attachments respectively.
- `risk_scan_jobs → risk_logs`: a job has zero or one result and a deferred consistency trigger requires the result and succeeded state to commit together.
- `moderation_reviews`: partial root uniqueness and predecessor uniqueness form one nonbranching chain per revision; a correction must name the current chain head.
- `risk_models`/`risk_rulesets`: there may be many registered versions, but each has at most one active row, and active configuration must be compatible.
- Campaign/product receipts are many-to-many membership records, with `(campaign_id, product_id)` as their composite primary key.
- `django_session` has no user foreign key because Django stores framework session data; authorization must decode/validate it through Django.

Regenerate these sources after schema edits with `python docs/database/generate_reference.py`. Mermaid renders in Markdown viewers that support it. The source files can also be imported into Mermaid tooling for SVG/PDF export.
