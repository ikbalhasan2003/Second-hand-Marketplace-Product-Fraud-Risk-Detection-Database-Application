# Relational Schema

Notation: `PK` is the primary key, `AK` an alternate/unique key, and `FK` a foreign key. Nullable columns are marked `?` in relation signatures. Complete types, defaults, checks and indexes are in the [data dictionary](DATA_DICTIONARY.md).

Every foreign-key component is significant. In particular, revision references use `(product_id, revision_no)`, not either field alone. All references retain history through `NO ACTION` or explicit `RESTRICT`; the product's current-revision reference alone is deferred to transaction end.

## `marketplace_settings`

```text
marketplace_settings(
  singleton,
  currency,
  unanswered_order_timeout,
  refresh_timezone
)
PK (singleton)
```

## `users`

```text
users(
  user_id,
  email,
  password,
  full_name,
  location?,
  private_contact?,
  status,
  is_active,
  is_staff,
  is_superuser,
  last_login?,
  created_at,
  deactivated_at?
)
PK (user_id)
CONDITIONAL/EXPRESSION AK: CREATE UNIQUE INDEX users_email_ci_uq ON users (lower(email))
```

## `django_content_type`

```text
django_content_type(
  id,
  app_label,
  model
)
PK (id)
AK UNIQUE (app_label,model)
```

## `auth_permission`

```text
auth_permission(
  id,
  name,
  content_type_id,
  codename
)
PK (id)
FK (content_type_id) REFERENCES django_content_type(id)
AK UNIQUE (content_type_id,codename)
```

## `auth_group`

```text
auth_group(
  id,
  name
)
PK (id)
AK UNIQUE (name)
```

## `auth_group_permissions`

```text
auth_group_permissions(
  id,
  group_id,
  permission_id
)
PK (id)
FK (group_id) REFERENCES auth_group(id)
FK (permission_id) REFERENCES auth_permission(id)
AK UNIQUE(group_id,permission_id)
```

## `users_groups`

```text
users_groups(
  id,
  user_id,
  group_id
)
PK (id)
FK (user_id) REFERENCES users(user_id)
FK (group_id) REFERENCES auth_group(id)
AK UNIQUE(user_id,group_id)
```

## `users_user_permissions`

```text
users_user_permissions(
  id,
  user_id,
  permission_id
)
PK (id)
FK (user_id) REFERENCES users(user_id)
FK (permission_id) REFERENCES auth_permission(id)
AK UNIQUE(user_id,permission_id)
```

## `django_session`

```text
django_session(
  session_key,
  session_data,
  expire_date
)
PK (session_key)
```

## `categories`

```text
categories(
  category_id,
  name,
  description,
  is_active
)
PK (category_id)
```

## `products`

```text
products(
  product_id,
  seller_id,
  current_revision_no?,
  availability,
  visibility,
  context_version,
  first_published_at?,
  created_at,
  updated_at
)
PK (product_id)
FK (seller_id) REFERENCES users(user_id)
FK (product_id, current_revision_no) REFERENCES product_revisions(product_id, revision_no)
```

## `product_revisions`

```text
product_revisions(
  product_id,
  revision_no,
  category_id,
  title,
  description,
  price,
  original_price?,
  currency,
  condition,
  location,
  text_fingerprint,
  created_at,
  created_xid
)
PK (product_id, revision_no)
FK (product_id) REFERENCES products(product_id)
FK (category_id) REFERENCES categories(category_id)
```

## `product_images`

```text
product_images(
  image_id,
  product_id,
  revision_no,
  storage_key,
  sort_order,
  content_type,
  byte_size,
  content_sha256,
  width,
  height,
  uploaded_at
)
PK (image_id)
FK (product_id, revision_no) REFERENCES product_revisions(product_id, revision_no)
AK UNIQUE(product_id,revision_no,sort_order)
AK UNIQUE (storage_key)
```

## `conversations`

```text
conversations(
  conversation_id,
  product_id,
  buyer_id,
  created_at
)
PK (conversation_id)
FK (product_id) REFERENCES products(product_id)
FK (buyer_id) REFERENCES users(user_id)
AK UNIQUE(product_id,buyer_id)
```

## `chat_messages`

```text
chat_messages(
  message_id,
  conversation_id,
  sender_id,
  message_text,
  sent_at,
  read_at?
)
PK (message_id)
FK (conversation_id) REFERENCES conversations(conversation_id)
FK (sender_id) REFERENCES users(user_id)
```

## `transactions`

```text
transactions(
  transaction_id,
  product_id,
  revision_no,
  buyer_id,
  status,
  request_key,
  request_fingerprint,
  created_at,
  updated_at
)
PK (transaction_id)
FK (buyer_id) REFERENCES users(user_id)
FK (product_id, revision_no) REFERENCES product_revisions(product_id, revision_no)
AK UNIQUE(buyer_id,request_key)
AK UNIQUE(transaction_id,product_id,revision_no,buyer_id)
```

## `order_status_history`

```text
order_status_history(
  event_id,
  transaction_id,
  from_status?,
  to_status,
  actor_id?,
  system_actor?,
  reason,
  occurred_at
)
PK (event_id)
FK (transaction_id) REFERENCES transactions(transaction_id)
FK (actor_id) REFERENCES users(user_id)
```

## `fraud_reports`

```text
fraud_reports(
  report_id,
  product_id,
  revision_no,
  reporter_id,
  transaction_id?,
  reason_code,
  comment,
  status,
  assigned_admin_id?,
  public_outcome?,
  created_at,
  resolved_at?
)
PK (report_id)
FK (reporter_id) REFERENCES users(user_id)
FK (assigned_admin_id) REFERENCES users(user_id)
FK (product_id, revision_no) REFERENCES product_revisions(product_id, revision_no)
FK (transaction_id, product_id, revision_no, reporter_id) REFERENCES transactions(transaction_id, product_id, revision_no, buyer_id)
AK UNIQUE(report_id,product_id,revision_no)
```

## `report_attachments`

```text
report_attachments(
  attachment_id,
  report_id,
  storage_key,
  sort_order,
  content_type,
  byte_size,
  content_sha256,
  uploaded_at
)
PK (attachment_id)
FK (report_id) REFERENCES fraud_reports(report_id)
AK UNIQUE(report_id,sort_order)
AK UNIQUE (storage_key)
```

## `moderation_reviews`

```text
moderation_reviews(
  review_id,
  product_id,
  revision_no,
  report_id?,
  reviewer_id,
  verdict,
  reason,
  evidence_summary,
  supersedes_review_id?,
  reviewed_at
)
PK (review_id)
FK (reviewer_id) REFERENCES users(user_id)
FK (product_id, revision_no) REFERENCES product_revisions(product_id, revision_no)
FK (report_id, product_id, revision_no) REFERENCES fraud_reports(report_id, product_id, revision_no)
FK (supersedes_review_id, product_id, revision_no) REFERENCES moderation_reviews(review_id, product_id, revision_no)
AK UNIQUE(review_id,product_id,revision_no)
AK UNIQUE (supersedes_review_id)
```

## `admin_audit_logs`

```text
admin_audit_logs(
  audit_id,
  admin_id,
  action_type,
  user_id?,
  product_id?,
  report_id?,
  review_id?,
  transaction_id?,
  model_id?,
  ruleset_id?,
  dataset_id?,
  reason,
  before_data,
  after_data,
  occurred_at
)
PK (audit_id)
FK (admin_id) REFERENCES users(user_id)
FK (user_id) REFERENCES users(user_id)
FK (product_id) REFERENCES products(product_id)
FK (report_id) REFERENCES fraud_reports(report_id)
FK (review_id) REFERENCES moderation_reviews(review_id)
FK (transaction_id) REFERENCES transactions(transaction_id)
FK (model_id) REFERENCES risk_models(model_id)
FK (ruleset_id) REFERENCES risk_rulesets(ruleset_id)
FK (dataset_id) REFERENCES dataset_versions(dataset_id)
```

## `seller_appeals`

```text
seller_appeals(
  appeal_id,
  review_id,
  seller_id,
  reason,
  status,
  assigned_admin_id?,
  outcome?,
  created_at,
  resolved_at?
)
PK (appeal_id)
FK (review_id) REFERENCES moderation_reviews(review_id)
FK (seller_id) REFERENCES users(user_id)
FK (assigned_admin_id) REFERENCES users(user_id)
```

## `notifications`

```text
notifications(
  notification_id,
  recipient_id,
  source_event_key,
  summary,
  product_id?,
  transaction_id?,
  report_id?,
  created_at,
  read_at?
)
PK (notification_id)
FK (recipient_id) REFERENCES users(user_id)
FK (product_id) REFERENCES products(product_id)
FK (transaction_id) REFERENCES transactions(transaction_id)
FK (report_id) REFERENCES fraud_reports(report_id)
AK UNIQUE(recipient_id,source_event_key)
```

## `feature_schemas`

```text
feature_schemas(
  feature_schema_id,
  version,
  definition,
  code_revision,
  created_at
)
PK (feature_schema_id)
AK UNIQUE (version)
```

## `dataset_sources`

```text
dataset_sources(
  source_id,
  source_key,
  source_type,
  attribution,
  license_access_notes,
  source_uri?,
  created_at
)
PK (source_id)
AK UNIQUE (source_key)
```

## `dataset_versions`

```text
dataset_versions(
  dataset_id,
  version,
  feature_schema_id,
  state,
  generator_version?,
  seed,
  export_cutoff,
  split_strategy,
  manifest_key?,
  dataset_sha256?,
  created_by,
  created_at,
  frozen_at?
)
PK (dataset_id)
FK (feature_schema_id) REFERENCES feature_schemas(feature_schema_id)
FK (created_by) REFERENCES users(user_id)
AK UNIQUE (version)
```

## `dataset_split_groups`

```text
dataset_split_groups(
  split_group_id,
  dataset_id,
  group_key,
  partition
)
PK (dataset_id, split_group_id)
FK (dataset_id) REFERENCES dataset_versions(dataset_id)
AK UNIQUE (dataset_id, group_key)
```

## `dataset_records`

```text
dataset_records(
  record_id,
  dataset_id,
  record_key,
  source_id,
  split_group_id,
  product_id?,
  revision_no?,
  review_id?,
  seller_group_key,
  template_family_key?,
  duplicate_group_key?,
  feature_as_of,
  feature_values,
  label,
  label_source,
  label_decided_at,
  is_synthetic,
  scenario_version?
)
PK (record_id)
FK (dataset_id) REFERENCES dataset_versions(dataset_id)
FK (source_id) REFERENCES dataset_sources(source_id)
FK (review_id) REFERENCES moderation_reviews(review_id)
FK (dataset_id, split_group_id) REFERENCES dataset_split_groups(dataset_id, split_group_id)
FK (product_id, revision_no) REFERENCES product_revisions(product_id, revision_no)
AK UNIQUE (dataset_id, record_key)
```

## `risk_models`

```text
risk_models(
  model_id,
  version,
  feature_schema_id,
  dataset_id,
  algorithm,
  artifact_key,
  artifact_sha256,
  seed,
  class_mapping,
  dependency_manifest,
  code_revision,
  state,
  registered_by,
  registered_at
)
PK (model_id)
FK (feature_schema_id) REFERENCES feature_schemas(feature_schema_id)
FK (dataset_id) REFERENCES dataset_versions(dataset_id)
FK (registered_by) REFERENCES users(user_id)
AK UNIQUE (version)
AK UNIQUE (artifact_key)
CONDITIONAL/EXPRESSION AK: CREATE UNIQUE INDEX risk_models_one_active ON risk_models ((TRUE)) WHERE state = 'active'
```

## `model_evaluations`

```text
model_evaluations(
  evaluation_id,
  model_id,
  partition,
  slice_key,
  sample_count,
  fraud_count,
  true_positive,
  false_positive,
  true_negative,
  false_negative,
  average_precision?,
  report_key,
  evaluated_at
)
PK (evaluation_id)
FK (model_id) REFERENCES risk_models(model_id)
AK UNIQUE (model_id, partition, slice_key)
```

## `risk_rulesets`

```text
risk_rulesets(
  ruleset_id,
  version,
  feature_schema_id,
  state,
  max_assessment_age,
  created_by,
  published_by?,
  created_at,
  published_at?
)
PK (ruleset_id)
FK (feature_schema_id) REFERENCES feature_schemas(feature_schema_id)
FK (created_by) REFERENCES users(user_id)
FK (published_by) REFERENCES users(user_id)
AK UNIQUE (version)
CONDITIONAL/EXPRESSION AK: CREATE UNIQUE INDEX risk_rulesets_one_active ON risk_rulesets ((TRUE)) WHERE state = 'active'
```

## `risk_rules`

```text
risk_rules(
  rule_id,
  ruleset_id,
  rule_key,
  numeric_value,
  description
)
PK (rule_id)
FK (ruleset_id) REFERENCES risk_rulesets(ruleset_id)
AK UNIQUE (ruleset_id, rule_key)
```

## `risk_scan_jobs`

```text
risk_scan_jobs(
  job_id,
  product_id,
  revision_no,
  context_version,
  model_id?,
  ruleset_id?,
  feature_schema_id?,
  source_event_key?,
  status,
  attempts,
  claim_token?,
  retry_at,
  lease_expires_at?,
  feature_as_of?,
  feature_snapshot?,
  error_code?,
  created_at,
  updated_at,
  completed_at?
)
PK (job_id)
FK (model_id) REFERENCES risk_models(model_id)
FK (ruleset_id) REFERENCES risk_rulesets(ruleset_id)
FK (feature_schema_id) REFERENCES feature_schemas(feature_schema_id)
FK (product_id, revision_no) REFERENCES product_revisions(product_id, revision_no)
AK UNIQUE (source_event_key)
```

## `risk_logs`

```text
risk_logs(
  risk_id,
  job_id,
  risk_score,
  risk_level,
  observed_factors,
  model_explanation?,
  predicted_at
)
PK (risk_id)
FK (job_id) REFERENCES risk_scan_jobs(job_id)
AK UNIQUE (job_id)
```

## `risk_rescan_campaigns`

```text
risk_rescan_campaigns(
  campaign_id,
  source_event_key,
  event_type,
  source_audit_id?,
  seller_id?,
  target_product_id?,
  cutoff_product_id,
  cutoff_at,
  refresh_date?,
  refresh_timezone?,
  status,
  cursor_product_id,
  attempts,
  error_code?,
  created_at,
  completed_at?
)
PK (campaign_id)
FK (source_audit_id) REFERENCES admin_audit_logs(audit_id)
FK (seller_id) REFERENCES users(user_id)
FK (target_product_id) REFERENCES products(product_id)
AK UNIQUE (source_event_key)
AK UNIQUE (source_audit_id)
```

## `risk_rescan_events`

```text
risk_rescan_events(
  campaign_id,
  product_id,
  job_id,
  created_at
)
PK (campaign_id, product_id)
FK (campaign_id) REFERENCES risk_rescan_campaigns(campaign_id)
FK (product_id) REFERENCES products(product_id)
FK (job_id) REFERENCES risk_scan_jobs(job_id)
```

## `embedding_models`

```text
embedding_models(
  embedding_model_id,
  version,
  model_name,
  model_revision,
  dimensions,
  text_policy,
  dependency_manifest,
  registered_by,
  created_at
)
PK (embedding_model_id)
FK (registered_by) REFERENCES users(user_id)
AK UNIQUE (version)
```

## `review_embedding`

```text
review_embedding(
  review_embedding_id,
  review_id,
  embedding_model_id,
  content_sha256,
  embedding,
  created_at
)
PK (review_embedding_id)
FK (review_id) REFERENCES moderation_reviews(review_id)
FK (embedding_model_id) REFERENCES embedding_models(embedding_model_id)
AK UNIQUE(review_id, embedding_model_id)
```

## Read models

| View/function | Meaning |
| --- | --- |
| `risk_score_history` | Every successful prediction joined to its pinned target/configuration |
| `fraud_logs` | Historical high-risk AI predictions; does not mean confirmed fraud |
| `current_listing_risk` | Read-time current score and five assessment states |
| `effective_reviews_at(cutoff)` | Canonical latest decision per revision as known by cutoff, including unresolved |
| `latest_effective_reviews` | Canonical decisions as of the current statement |
| `eligible_training_labels` | Latest evidence-backed fraud/legitimate decisions; unresolved is excluded |
| `admin_review_queue` | One row per listing combining open cases and current high risk |
| `seller_order_history` | Ordered revision terms and current order status; caller filters seller ownership |
| `model_evaluation_metrics` | Precision, recall and F1 derived from stored confusion counts |

Views do not provide per-browser-user authorization. They are internal query models, with runtime grants and authenticated query filters applied separately.
