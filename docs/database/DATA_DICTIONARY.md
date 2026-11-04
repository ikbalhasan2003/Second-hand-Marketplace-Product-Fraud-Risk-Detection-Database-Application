# Database Data Dictionary

Generated from the reviewed CREATE TABLE definitions with `python docs/database/generate_reference.py`. Exact DDL, indexes and checks are retained below. Trigger behavior is described in [Database Design](../../DATABASE_DESIGN.md) and the SQL function files. This generator documents SQL; it does not validate or execute it.

**Physical relations:** 38 tables including Django infrastructure, P1 structures, AI provenance, and optional P2 tables when present. Core scripts do not install the optional vector extension.

All unqualified foreign keys use PostgreSQL's default `ON UPDATE NO ACTION`. An omitted delete clause means `ON DELETE NO ACTION`; explicit `RESTRICT` is shown. The current-revision foreign key is `DEFERRABLE INITIALLY DEFERRED`; other foreign keys are immediate unless SQL says otherwise.

Nullability is physical SQL nullability. Additional relationships become mandatory in particular lifecycle states through checks/triggers. A field described as an identifier is explained by the Key/reference column and foreign-key list.

## `marketplace_settings`

Singleton deployment policy: one currency, unanswered-order expiry and scheduled refresh timezone.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(singleton)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `singleton` | `boolean` | no | `true` | PK | Boolean primary key constrained true: at most one configuration row. |
| `currency` | `char(3)` | no | — | — | Uppercase three-letter currency code; publication service enforces demo configuration. |
| `unanswered_order_timeout` | `interval` | no | `interval '48 hours'` | — | Positive duration before an unanswered placed order may expire. |
| `refresh_timezone` | `varchar(80)` | no | `'Asia/Shanghai'` | — | Configured timezone for deterministic daily-refresh date identity. |

**Checks, alternate keys and foreign keys**

```sql
singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton)
currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$')
unanswered_order_timeout interval NOT NULL DEFAULT interval '48 hours' CHECK (unanswered_order_timeout > interval '0')
```

## `users`

Shared identity, Django credentials and marketplace account status.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(user_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `user_id` | `bigint` | no | `identity` | PK | Shared user identity; role-specific meaning follows the relationship. |
| `email` | `varchar(254)` | no | — | — | Trimmed login email; lower(email) is unique. |
| `password` | `varchar(128)` | no | — | — | Django encoded password hash, never a plaintext password. |
| `full_name` | `varchar(150)` | no | — | — | Account display name; no duplicate name uniqueness requirement. |
| `location` | `varchar(150)` | yes | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `private_contact` | `varchar(100)` | yes | — | — | Private contact value, excluded from public profiles/ML exports. |
| `status` | `varchar(16)` | no | `'active'` | — | Constrained workflow/account/queue state; see checks and trigger contract. |
| `is_active` | `boolean` | no | `true` | — | Authentication flag for users; catalog-enabled flag for categories. |
| `is_staff` | `boolean` | no | `false` | — | Django administration flag; not a substitute for administrator membership. |
| `is_superuser` | `boolean` | no | `false` | — | Trusted Django superuser flag; never client assignable. |
| `last_login` | `timestamptz` | yes | — | — | Last login. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `deactivated_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
email varchar(254) NOT NULL CHECK (email = btrim(email) AND position('@' IN email) > 1)
full_name varchar(150) NOT NULL CHECK (length(btrim(full_name)) > 0)
status varchar(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active','blocked','deactivated'))
CHECK ((status = 'deactivated') = (deactivated_at IS NOT NULL))
```

**Additional indexes**

```sql
CREATE UNIQUE INDEX users_email_ci_uq ON users (lower(email))
```

## `django_content_type`

Django model identities used by permissions.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `id` | `integer` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `app_label` | `varchar(100)` | no | — | — | App label. |
| `model` | `varchar(100)` | no | — | — | Model. |

**Checks, alternate keys and foreign keys**

```sql
UNIQUE (app_label,model)
```

## `auth_permission`

Named permission scoped to a Django content type.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `id` | `integer` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `name` | `varchar(255)` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `content_type_id` | `integer` | no | — | FK part → django_content_type(id) | Relational identifier; primary/foreign key role is shown alongside. |
| `codename` | `varchar(100)` | no | — | — | Codename. |

**Checks, alternate keys and foreign keys**

```sql
UNIQUE (content_type_id,codename)
content_type_id integer NOT NULL REFERENCES django_content_type(id)
```

## `auth_group`

Role/group names; buyer, seller and administrator are provisioned groups.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `id` | `integer` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `name` | `varchar(150)` | no | — | UNIQUE | Required/optional descriptive value; bounds and rules follow the SQL constraints. |

**Checks, alternate keys and foreign keys**

```sql
```

## `auth_group_permissions`

Unique group-to-permission junction.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `group_id` | `integer` | no | — | FK part → auth_group(id) | Relational identifier; primary/foreign key role is shown alongside. |
| `permission_id` | `integer` | no | — | FK part → auth_permission(id) | Relational identifier; primary/foreign key role is shown alongside. |

**Checks, alternate keys and foreign keys**

```sql
UNIQUE(group_id,permission_id)
group_id integer NOT NULL REFERENCES auth_group(id)
permission_id integer NOT NULL REFERENCES auth_permission(id)
```

## `users_groups`

Single source of user role/group membership.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `user_id` | `bigint` | no | — | FK part → users(user_id) | Shared user identity; role-specific meaning follows the relationship. |
| `group_id` | `integer` | no | — | FK part → auth_group(id) | Relational identifier; primary/foreign key role is shown alongside. |

**Checks, alternate keys and foreign keys**

```sql
UNIQUE(user_id,group_id)
user_id bigint NOT NULL REFERENCES users(user_id)
group_id integer NOT NULL REFERENCES auth_group(id)
```

## `users_user_permissions`

Explicit Django per-user permission junction.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `user_id` | `bigint` | no | — | FK part → users(user_id) | Shared user identity; role-specific meaning follows the relationship. |
| `permission_id` | `integer` | no | — | FK part → auth_permission(id) | Relational identifier; primary/foreign key role is shown alongside. |

**Checks, alternate keys and foreign keys**

```sql
UNIQUE(user_id,permission_id)
user_id bigint NOT NULL REFERENCES users(user_id)
permission_id integer NOT NULL REFERENCES auth_permission(id)
```

## `django_session`

Django database-backed sessions; session payload is framework encoded.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(session_key)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `session_key` | `varchar(40)` | no | — | PK | Framework session lookup token; never exported or logged. |
| `session_data` | `text` | no | — | — | Framework-encoded session payload. |
| `expire_date` | `timestamptz` | no | — | — | Session expiration instant for controlled cleanup. |

**Checks, alternate keys and foreign keys**

```sql
```

## `categories`

Reusable category identity and display metadata.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(category_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `category_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `name` | `varchar(100)` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `description` | `text` | no | `''` | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `is_active` | `boolean` | no | `true` | — | Authentication flag for users; catalog-enabled flag for categories. |

**Checks, alternate keys and foreign keys**

```sql
name varchar(100) NOT NULL CHECK (length(btrim(name)) > 0)
```

## `products`

Stable listing identity, seller ownership and mutable workflow/context state.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(product_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `product_id` | `bigint` | no | `identity` | PK; FK part → product_revisions(product_id, revision_no) | Stable product identity; paired with revision_no for historical content. |
| `seller_id` | `bigint` | no | — | FK part → users(user_id) | Owning/scoped seller identity; orders derive ownership from product. |
| `current_revision_no` | `integer` | yes | — | FK part → product_revisions(product_id, revision_no) | Current content pointer; paired with this product_id. |
| `availability` | `varchar(16)` | no | `'draft'` | — | draft/available/reserved/sold; synchronized with order state. |
| `visibility` | `varchar(24)` | no | `'visible'` | — | Public/seller/admin removal state, independent of availability. |
| `context_version` | `bigint` | no | `0` | — | Assessment evidence/refresh generation, independent of content revision. |
| `first_published_at` | `timestamptz` | yes | — | — | Immutable first publication instant used by rolling-window features. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `updated_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
availability varchar(16) NOT NULL DEFAULT 'draft' CHECK (availability IN ('draft','available','reserved','sold'))
visibility varchar(24) NOT NULL DEFAULT 'visible' CHECK (visibility IN ('visible','removed_by_seller','removed_by_admin'))
context_version bigint NOT NULL DEFAULT 0 CHECK (context_version >= 0)
CHECK (availability = 'draft' OR (current_revision_no IS NOT NULL AND first_published_at IS NOT NULL))
ADD CONSTRAINT products_current_revision_fk FOREIGN KEY(product_id,current_revision_no) REFERENCES product_revisions(product_id,revision_no) DEFERRABLE INITIALLY DEFERRED
seller_id bigint NOT NULL REFERENCES users(user_id)
```

## `product_revisions`

Immutable listing content keyed by product and revision number.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(product_id, revision_no)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `product_id` | `bigint` | no | — | PK; FK part → products(product_id) | Stable product identity; paired with revision_no for historical content. |
| `revision_no` | `integer` | no | — | PK | Positive revision sequence unique within a product. |
| `category_id` | `bigint` | no | — | FK part → categories(category_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `title` | `varchar(200)` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `description` | `text` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `price` | `numeric(12,2)` | no | — | — | Positive exact decimal listing price at this revision. |
| `original_price` | `numeric(12,2)` | yes | — | — | Optional nonnegative comparison price, without a claim that it was verified. |
| `currency` | `char(3)` | no | — | — | Uppercase three-letter currency code; publication service enforces demo configuration. |
| `condition` | `varchar(16)` | no | — | — | like_new/good/fair/poor product condition at this revision. |
| `location` | `varchar(150)` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `text_fingerprint` | `varchar(64)` | no | — | — | SHA-256 normalized-text fingerprint; extraction rules are versioned. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `created_xid` | `xid8` | no | `pg_current_xact_id()` | — | Internal creation-transaction marker: image association inserts must occur in that transaction. |

**Checks, alternate keys and foreign keys**

```sql
revision_no integer NOT NULL CHECK (revision_no > 0)
title varchar(200) NOT NULL CHECK (length(btrim(title)) > 0)
description text NOT NULL CHECK (length(description) BETWEEN 1 AND 20000)
price numeric(12,2) NOT NULL CHECK (price > 0 AND price <> 'NaN'::numeric)
original_price numeric(12,2) CHECK (original_price >= 0 AND original_price <> 'NaN'::numeric)
currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$')
condition varchar(16) NOT NULL CHECK (condition IN ('like_new','good','fair','poor'))
location varchar(150) NOT NULL CHECK (length(btrim(location)) > 0)
text_fingerprint varchar(64) NOT NULL CHECK (text_fingerprint ~ '^[0-9a-f]{64}$')
PRIMARY KEY (product_id,revision_no)
product_id bigint NOT NULL REFERENCES products(product_id)
category_id bigint NOT NULL REFERENCES categories(category_id)
```

**Additional indexes**

```sql
CREATE INDEX revisions_search_gin ON product_revisions USING gin (to_tsvector('simple'::regconfig,title || ' ' || description))
```

## `product_images`

Immutable per-revision image association and validated file metadata.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(image_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `image_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `product_id` | `bigint` | no | — | FK part → product_revisions(product_id, revision_no) | Stable product identity; paired with revision_no for historical content. |
| `revision_no` | `integer` | no | — | FK part → product_revisions(product_id, revision_no) | Positive revision sequence unique within a product. |
| `storage_key` | `varchar(500)` | no | — | UNIQUE | Generated immutable file locator; no user-supplied public evidence URL. |
| `sort_order` | `smallint` | no | — | — | Bounded position, unique within its parent; implements image-count cap. |
| `content_type` | `varchar(32)` | no | — | — | Allowed image MIME type; actual bytes still require Pillow validation. |
| `byte_size` | `integer` | no | — | — | File size, one byte through 5 MiB. |
| `content_sha256` | `char(64)` | no | — | — | SHA-256 of the stored file contents. |
| `width` | `integer` | no | — | — | Positive decoded image width in pixels. |
| `height` | `integer` | no | — | — | Positive decoded image height in pixels. |
| `uploaded_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
sort_order smallint NOT NULL CHECK (sort_order BETWEEN 0 AND 5)
content_type varchar(32) NOT NULL CHECK (content_type IN ('image/jpeg','image/png','image/webp'))
byte_size integer NOT NULL CHECK (byte_size BETWEEN 1 AND 5242880)
content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$')
width integer NOT NULL CHECK (width > 0)
height integer NOT NULL CHECK (height > 0)
FOREIGN KEY(product_id,revision_no) REFERENCES product_revisions(product_id,revision_no)
UNIQUE(product_id,revision_no,sort_order)
```

## `conversations`

One private conversation per product/interested buyer pair.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(conversation_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `conversation_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `product_id` | `bigint` | no | — | FK part → products(product_id) | Stable product identity; paired with revision_no for historical content. |
| `buyer_id` | `bigint` | no | — | FK part → users(user_id) | Buyer participant/account identity. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
UNIQUE(product_id,buyer_id)
product_id bigint NOT NULL REFERENCES products(product_id)
buyer_id bigint NOT NULL REFERENCES users(user_id)
```

## `chat_messages`

Retained participant messages with recipient-controlled initial read receipt.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(message_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `message_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `conversation_id` | `bigint` | no | — | FK part → conversations(conversation_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `sender_id` | `bigint` | no | — | FK part → users(user_id) | Message sender; trigger requires a live authorized participant. |
| `message_text` | `text` | no | — | — | Escaped-on-display message body, 1..4000 trimmed characters. |
| `sent_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `read_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
message_text text NOT NULL CHECK (length(btrim(message_text)) BETWEEN 1 AND 4000)
CHECK (read_at IS NULL OR read_at >= sent_at)
conversation_id bigint NOT NULL REFERENCES conversations(conversation_id)
sender_id bigint NOT NULL REFERENCES users(user_id)
```

## `transactions`

Purchase/fulfilment agreement against immutable listing terms; no payment verification.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(transaction_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `transaction_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `product_id` | `bigint` | no | — | FK part → product_revisions(product_id, revision_no) | Stable product identity; paired with revision_no for historical content. |
| `revision_no` | `integer` | no | — | FK part → product_revisions(product_id, revision_no) | Positive revision sequence unique within a product. |
| `buyer_id` | `bigint` | no | — | FK part → users(user_id) | Buyer participant/account identity. |
| `status` | `varchar(16)` | no | `'placed'` | — | Constrained workflow/account/queue state; see checks and trigger contract. |
| `request_key` | `uuid` | no | — | — | Client request UUID scoped to the buyer for order idempotency. |
| `request_fingerprint` | `char(64)` | no | — | — | SHA-256 of canonical request data; mismatched key replay fails. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `updated_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
status varchar(16) NOT NULL DEFAULT 'placed' CHECK (status IN ('placed','accepted','shipped','disputed','completed','cancelled'))
request_fingerprint char(64) NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$')
FOREIGN KEY(product_id,revision_no) REFERENCES product_revisions(product_id,revision_no)
UNIQUE(buyer_id,request_key)
UNIQUE(transaction_id,product_id,revision_no,buyer_id)
buyer_id bigint NOT NULL REFERENCES users(user_id)
```

## `order_status_history`

Append-only initial order event and subsequent state transitions.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(event_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `event_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `transaction_id` | `bigint` | no | — | FK part → transactions(transaction_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `from_status` | `varchar(16)` | yes | — | — | Prior order state; null only for the initial event. |
| `to_status` | `varchar(16)` | no | — | — | New order state recorded by this immutable event. |
| `actor_id` | `bigint` | yes | — | FK part → users(user_id) | User actor, mutually exclusive with a system actor. |
| `system_actor` | `varchar(40)` | yes | — | — | Named scheduled/system actor when no browser-user actor applies. |
| `reason` | `text` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `occurred_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
from_status varchar(16) CHECK (from_status IN ('placed','accepted','shipped','disputed','completed','cancelled'))
to_status varchar(16) NOT NULL CHECK (to_status IN ('placed','accepted','shipped','disputed','completed','cancelled'))
CHECK ((actor_id IS NULL) <> (system_actor IS NULL))
CHECK (from_status IS DISTINCT FROM to_status)
transaction_id bigint NOT NULL REFERENCES transactions(transaction_id)
actor_id bigint REFERENCES users(user_id)
```

## `fraud_reports`

Buyer allegation/case workflow against a specific revision.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(report_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `report_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `product_id` | `bigint` | no | — | FK part → product_revisions(product_id, revision_no); FK part → transactions(transaction_id, product_id, revision_no, buyer_id) | Stable product identity; paired with revision_no for historical content. |
| `revision_no` | `integer` | no | — | FK part → product_revisions(product_id, revision_no); FK part → transactions(transaction_id, product_id, revision_no, buyer_id) | Positive revision sequence unique within a product. |
| `reporter_id` | `bigint` | no | — | FK part → users(user_id); FK part → transactions(transaction_id, product_id, revision_no, buyer_id) | Buyer who submitted the allegation and owns its private evidence. |
| `transaction_id` | `bigint` | yes | — | FK part → transactions(transaction_id, product_id, revision_no, buyer_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `reason_code` | `varchar(32)` | no | — | — | Controlled allegation category, independent of an adjudicated verdict. |
| `comment` | `text` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `status` | `varchar(16)` | no | `'pending'` | — | Constrained workflow/account/queue state; see checks and trigger contract. |
| `assigned_admin_id` | `bigint` | yes | — | FK part → users(user_id) | Optional administrator assigned to the workflow. |
| `public_outcome` | `text` | yes | — | — | Reporter-facing moderation outcome; exclude private internal evidence. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `resolved_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
reason_code varchar(32) NOT NULL CHECK (reason_code IN ('misleading_description','suspicious_price','duplicate_listing','non_delivery','counterfeit','other'))
comment text NOT NULL CHECK (length(btrim(comment)) BETWEEN 1 AND 5000)
status varchar(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','reviewing','resolved','dismissed'))
FOREIGN KEY(product_id,revision_no) REFERENCES product_revisions(product_id,revision_no)
FOREIGN KEY(transaction_id,product_id,revision_no,reporter_id) REFERENCES transactions(transaction_id,product_id,revision_no,buyer_id)
UNIQUE(report_id,product_id,revision_no)
CHECK ((status IN ('resolved','dismissed')) = (resolved_at IS NOT NULL))
reporter_id bigint NOT NULL REFERENCES users(user_id)
assigned_admin_id bigint REFERENCES users(user_id)
```

## `report_attachments`

Private evidence images, limited to three distinct positions per case.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(attachment_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `attachment_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `report_id` | `bigint` | no | — | FK part → fraud_reports(report_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `storage_key` | `varchar(500)` | no | — | UNIQUE | Generated immutable file locator; no user-supplied public evidence URL. |
| `sort_order` | `smallint` | no | — | — | Bounded position, unique within its parent; implements image-count cap. |
| `content_type` | `varchar(32)` | no | — | — | Allowed image MIME type; actual bytes still require Pillow validation. |
| `byte_size` | `integer` | no | — | — | File size, one byte through 5 MiB. |
| `content_sha256` | `char(64)` | no | — | — | SHA-256 of the stored file contents. |
| `uploaded_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
sort_order smallint NOT NULL CHECK (sort_order BETWEEN 0 AND 2)
content_type varchar(32) NOT NULL CHECK (content_type IN ('image/jpeg','image/png','image/webp'))
byte_size integer NOT NULL CHECK (byte_size BETWEEN 1 AND 5242880)
content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$')
UNIQUE(report_id,sort_order)
report_id bigint NOT NULL REFERENCES fraud_reports(report_id)
```

## `moderation_reviews`

Canonical append-only evidence-backed decision chain per revision.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(review_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `review_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `product_id` | `bigint` | no | — | FK part → product_revisions(product_id, revision_no); FK part → fraud_reports(report_id, product_id, revision_no); FK part → moderation_reviews(review_id, product_id, revision_no) | Stable product identity; paired with revision_no for historical content. |
| `revision_no` | `integer` | no | — | FK part → product_revisions(product_id, revision_no); FK part → fraud_reports(report_id, product_id, revision_no); FK part → moderation_reviews(review_id, product_id, revision_no) | Positive revision sequence unique within a product. |
| `report_id` | `bigint` | yes | — | FK part → fraud_reports(report_id, product_id, revision_no) | Relational identifier; primary/foreign key role is shown alongside. |
| `reviewer_id` | `bigint` | no | — | FK part → users(user_id) | Administrator responsible for the decision. |
| `verdict` | `varchar(16)` | no | — | — | Human fraud/legitimate/unresolved decision; not a model score. |
| `reason` | `text` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `evidence_summary` | `text` | no | — | — | Required evidence basis; absence/dismissal of reports is insufficient. |
| `supersedes_review_id` | `bigint` | yes | — | UNIQUE; FK part → moderation_reviews(review_id, product_id, revision_no) | Immediate predecessor in the same revision's decision chain. |
| `reviewed_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
verdict varchar(16) NOT NULL CHECK (verdict IN ('fraud','legitimate','unresolved'))
reason text NOT NULL CHECK (length(btrim(reason)) > 0)
evidence_summary text NOT NULL CHECK (length(btrim(evidence_summary)) > 0)
FOREIGN KEY(product_id,revision_no) REFERENCES product_revisions(product_id,revision_no)
FOREIGN KEY(report_id,product_id,revision_no) REFERENCES fraud_reports(report_id,product_id,revision_no)
UNIQUE(review_id,product_id,revision_no)
FOREIGN KEY(supersedes_review_id,product_id,revision_no) REFERENCES moderation_reviews(review_id,product_id,revision_no)
CHECK (supersedes_review_id IS NULL OR supersedes_review_id <> review_id)
reviewer_id bigint NOT NULL REFERENCES users(user_id)
```

## `admin_audit_logs`

Append-only privileged-action accountability with typed target references.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(audit_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `audit_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `admin_id` | `bigint` | no | — | FK part → users(user_id) | Administrator who performed the audited action. |
| `action_type` | `varchar(64)` | no | — | — | Privileged operation kind used for audit and durable rescan obligations. |
| `user_id` | `bigint` | yes | — | FK part → users(user_id) | Shared user identity; role-specific meaning follows the relationship. |
| `product_id` | `bigint` | yes | — | FK part → products(product_id) | Stable product identity; paired with revision_no for historical content. |
| `report_id` | `bigint` | yes | — | FK part → fraud_reports(report_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `review_id` | `bigint` | yes | — | FK part → moderation_reviews(review_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `transaction_id` | `bigint` | yes | — | FK part → transactions(transaction_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `model_id` | `bigint` | yes | — | FK part → risk_models(model_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `ruleset_id` | `bigint` | yes | — | FK part → risk_rulesets(ruleset_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `dataset_id` | `bigint` | yes | — | FK part → dataset_versions(dataset_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `reason` | `text` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `before_data` | `jsonb` | no | `'{}'` | — | Bounded historical change evidence, excluding secrets/private messages. |
| `after_data` | `jsonb` | no | `'{}'` | — | Bounded historical change evidence, excluding secrets/private messages. |
| `occurred_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
reason text NOT NULL CHECK (length(btrim(reason)) > 0)
before_data jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(before_data) = 'object')
after_data jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(after_data) = 'object')
CHECK (num_nonnulls(user_id,product_id,report_id,review_id,transaction_id,model_id,ruleset_id,dataset_id) >= 1)
ADD CONSTRAINT audit_model_fk FOREIGN KEY(model_id) REFERENCES risk_models ON DELETE RESTRICT
ADD CONSTRAINT audit_ruleset_fk FOREIGN KEY(ruleset_id) REFERENCES risk_rulesets ON DELETE RESTRICT
ADD CONSTRAINT audit_dataset_fk FOREIGN KEY(dataset_id) REFERENCES dataset_versions ON DELETE RESTRICT
admin_id bigint NOT NULL REFERENCES users(user_id)
user_id bigint REFERENCES users(user_id)
product_id bigint REFERENCES products(product_id)
report_id bigint REFERENCES fraud_reports(report_id)
review_id bigint REFERENCES moderation_reviews(review_id)
transaction_id bigint REFERENCES transactions(transaction_id)
```

## `seller_appeals`

P1 seller challenge to a moderation decision; one open appeal per decision.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(appeal_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `appeal_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `review_id` | `bigint` | no | — | FK part → moderation_reviews(review_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `seller_id` | `bigint` | no | — | FK part → users(user_id) | Owning/scoped seller identity; orders derive ownership from product. |
| `reason` | `text` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `status` | `varchar(16)` | no | `'pending'` | — | Constrained workflow/account/queue state; see checks and trigger contract. |
| `assigned_admin_id` | `bigint` | yes | — | FK part → users(user_id) | Optional administrator assigned to the workflow. |
| `outcome` | `text` | yes | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `resolved_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
reason text NOT NULL CHECK (length(btrim(reason)) > 0)
status varchar(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','reviewing','upheld','corrected','withdrawn'))
CHECK ((status IN ('upheld','corrected','withdrawn')) = (resolved_at IS NOT NULL))
review_id bigint NOT NULL REFERENCES moderation_reviews(review_id)
seller_id bigint NOT NULL REFERENCES users(user_id)
assigned_admin_id bigint REFERENCES users(user_id)
```

## `notifications`

P1 in-app summary notices deduplicated per recipient/source event.

**Source:** [001_core.sql](../../database/001_core.sql) · **Primary key:** `(notification_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `notification_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `recipient_id` | `bigint` | no | — | FK part → users(user_id) | User authorized to receive this in-app notice. |
| `source_event_key` | `varchar(200)` | no | — | — | Stable source identity for retry/delivery deduplication. |
| `summary` | `varchar(500)` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |
| `product_id` | `bigint` | yes | — | FK part → products(product_id) | Stable product identity; paired with revision_no for historical content. |
| `transaction_id` | `bigint` | yes | — | FK part → transactions(transaction_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `report_id` | `bigint` | yes | — | FK part → fraud_reports(report_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `read_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
UNIQUE(recipient_id,source_event_key)
CHECK (read_at IS NULL OR read_at >= created_at)
recipient_id bigint NOT NULL REFERENCES users(user_id)
product_id bigint REFERENCES products(product_id)
transaction_id bigint REFERENCES transactions(transaction_id)
report_id bigint REFERENCES fraud_reports(report_id)
```

## `feature_schemas`

Immutable versioned feature-extraction contract and implementation revision.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(feature_schema_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `feature_schema_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `version` | `varchar(80)` | no | — | UNIQUE | Unique immutable version identity. |
| `definition` | `jsonb` | no | — | — | Versioned feature contract JSON object, validated by extractor implementation. |
| `code_revision` | `varchar(64)` | no | — | — | Source revision used to construct/extract/train this artifact. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
definition JSONB NOT NULL CHECK (jsonb_typeof(definition) = 'object')
```

## `dataset_sources`

Data origin, attribution and license/access provenance.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(source_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `source_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `source_key` | `varchar(100)` | no | — | UNIQUE | Source key. |
| `source_type` | `varchar(30)` | no | — | — | synthetic/project_review/external provenance category. |
| `attribution` | `text` | no | — | — | Source/author attribution retained with dataset provenance. |
| `license_access_notes` | `text` | no | — | — | License, permitted use or access restrictions; no inferred bulk-data right. |
| `source_uri` | `text` | yes | — | — | Optional provenance locator, not a download guarantee. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
source_type VARCHAR(30) NOT NULL CHECK (source_type IN ('synthetic','project_review','external'))
```

## `dataset_versions`

Dataset build/freeze lifecycle and immutable export manifest identity.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(dataset_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `dataset_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `version` | `varchar(100)` | no | — | UNIQUE | Unique immutable version identity. |
| `feature_schema_id` | `bigint` | no | — | FK part → feature_schemas(feature_schema_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `state` | `varchar(10)` | no | `'building'` | — | Configuration/dataset lifecycle state; see checks and immutability guard. |
| `generator_version` | `varchar(100)` | yes | — | — | Synthetic dataset generator version, when used. |
| `seed` | `bigint` | no | — | — | Reproducible random seed. |
| `export_cutoff` | `timestamptz` | no | — | — | Frozen upper observation/decision cutoff for the dataset export. |
| `split_strategy` | `text` | no | — | — | Description of group/temporal holdout policy and manifest. |
| `manifest_key` | `text` | yes | — | — | Stored dataset/split manifest locator. |
| `dataset_sha256` | `char(64)` | yes | — | — | Checksum of the frozen export. |
| `created_by` | `bigint` | no | — | FK part → users(user_id) | Created by. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `frozen_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
state VARCHAR(10) NOT NULL DEFAULT 'building' CHECK (state IN ('building','frozen'))
dataset_sha256 CHAR(64) CHECK (dataset_sha256 ~ '^[0-9a-f]{64}$')
CHECK ((state = 'building' AND frozen_at IS NULL) OR (state = 'frozen' AND frozen_at IS NOT NULL AND manifest_key IS NOT NULL AND dataset_sha256 IS NOT NULL))
feature_schema_id BIGINT NOT NULL REFERENCES feature_schemas ON DELETE RESTRICT
created_by BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT
```

## `dataset_split_groups`

Connected seller/template/duplicate group assigned to exactly one partition.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(dataset_id, split_group_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `split_group_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `dataset_id` | `bigint` | no | — | PK; FK part → dataset_versions(dataset_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `group_key` | `varchar(150)` | no | — | — | Pseudonymous connected grouping identity within a dataset. |
| `partition` | `varchar(10)` | no | — | — | train/validation/test/challenge split; dataset records derive it from their group. |

**Checks, alternate keys and foreign keys**

```sql
partition VARCHAR(10) NOT NULL CHECK (partition IN ('train','validation','test','challenge'))
PRIMARY KEY (dataset_id, split_group_id)
UNIQUE (dataset_id, group_key)
dataset_id BIGINT NOT NULL REFERENCES dataset_versions ON DELETE RESTRICT
```

## `dataset_records`

Versioned frozen features, labels and per-record provenance.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(record_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `dataset_id` | `bigint` | no | — | FK part → dataset_versions(dataset_id); FK part → dataset_split_groups(dataset_id, split_group_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `record_key` | `varchar(150)` | no | — | — | Stable record identity within the dataset version. |
| `source_id` | `bigint` | no | — | FK part → dataset_sources(source_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `split_group_id` | `bigint` | no | — | FK part → dataset_split_groups(dataset_id, split_group_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `product_id` | `bigint` | yes | — | FK part → product_revisions(product_id, revision_no) | Stable product identity; paired with revision_no for historical content. |
| `revision_no` | `integer` | yes | — | FK part → product_revisions(product_id, revision_no) | Positive revision sequence unique within a product. |
| `review_id` | `bigint` | yes | — | FK part → moderation_reviews(review_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `seller_group_key` | `varchar(150)` | no | — | — | Pseudonymous seller grouping key, excluding direct personal data. |
| `template_family_key` | `varchar(150)` | yes | — | — | Optional synthetic template/scenario family grouping key. |
| `duplicate_group_key` | `varchar(150)` | yes | — | — | Optional duplicate/variant grouping key for leakage checks. |
| `feature_as_of` | `timestamptz` | no | — | — | Point-in-time cutoff for frozen predictor facts. |
| `feature_values` | `jsonb` | no | — | — | Frozen versioned feature vector; metadata/label fields are separate. |
| `label` | `varchar(10)` | no | — | — | Eligible fraud/legitimate supervised target; unresolved records are excluded. |
| `label_source` | `text` | no | — | — | Decision/scenario source of the supervised target. |
| `label_decided_at` | `timestamptz` | no | — | — | When the label became known, distinct from predictor time. |
| `is_synthetic` | `boolean` | no | — | — | Explicit flag separating simulated records from real outcomes. |
| `scenario_version` | `varchar(100)` | yes | — | — | Generator/scenario version required for synthetic records. |

**Checks, alternate keys and foreign keys**

```sql
feature_values JSONB NOT NULL CHECK (jsonb_typeof(feature_values) = 'object')
label VARCHAR(10) NOT NULL CHECK (label IN ('fraud','legitimate'))
UNIQUE (dataset_id, record_key)
FOREIGN KEY (dataset_id, split_group_id) REFERENCES dataset_split_groups(dataset_id, split_group_id) ON DELETE RESTRICT
FOREIGN KEY (product_id, revision_no) REFERENCES product_revisions(product_id, revision_no) MATCH FULL ON DELETE RESTRICT
CHECK (feature_as_of <= label_decided_at)
CHECK (NOT is_synthetic OR scenario_version IS NOT NULL)
dataset_id BIGINT NOT NULL REFERENCES dataset_versions ON DELETE RESTRICT
source_id BIGINT NOT NULL REFERENCES dataset_sources ON DELETE RESTRICT
review_id BIGINT REFERENCES moderation_reviews ON DELETE RESTRICT
```

## `risk_models`

Trusted registered fitted model artifact and reproducibility metadata.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(model_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `model_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `version` | `varchar(100)` | no | — | UNIQUE | Unique immutable version identity. |
| `feature_schema_id` | `bigint` | no | — | FK part → feature_schemas(feature_schema_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `dataset_id` | `bigint` | no | — | FK part → dataset_versions(dataset_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `algorithm` | `varchar(40)` | no | — | — | random_forest/logistic_regression/rules_baseline experiment method. |
| `artifact_key` | `text` | no | — | UNIQUE | Immutable trusted model pipeline locator. |
| `artifact_sha256` | `char(64)` | no | — | — | SHA-256 verified before loading the trusted artifact. |
| `seed` | `bigint` | no | — | — | Reproducible random seed. |
| `class_mapping` | `jsonb` | no | — | — | Saved class identity mapping including fraud class. |
| `dependency_manifest` | `jsonb` | no | — | — | Exact training/inference package versions as structured metadata. |
| `code_revision` | `varchar(64)` | no | — | — | Source revision used to construct/extract/train this artifact. |
| `state` | `varchar(12)` | no | `'registered'` | — | Configuration/dataset lifecycle state; see checks and immutability guard. |
| `registered_by` | `bigint` | no | — | FK part → users(user_id) | Registered by. |
| `registered_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
algorithm VARCHAR(40) NOT NULL CHECK (algorithm IN ('random_forest','logistic_regression','rules_baseline'))
artifact_sha256 CHAR(64) NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$')
class_mapping JSONB NOT NULL CHECK (jsonb_typeof(class_mapping) = 'object' AND class_mapping ? 'fraud')
dependency_manifest JSONB NOT NULL CHECK (jsonb_typeof(dependency_manifest) = 'object')
state VARCHAR(12) NOT NULL DEFAULT 'registered' CHECK (state IN ('registered','active','retired'))
feature_schema_id BIGINT NOT NULL REFERENCES feature_schemas ON DELETE RESTRICT
dataset_id BIGINT NOT NULL REFERENCES dataset_versions ON DELETE RESTRICT
registered_by BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT
```

**Additional indexes**

```sql
CREATE UNIQUE INDEX risk_models_one_active ON risk_models ((TRUE)) WHERE state = 'active'
```

## `model_evaluations`

Measured evaluation slices; metrics derive from authoritative confusion counts.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(evaluation_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `evaluation_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `model_id` | `bigint` | no | — | FK part → risk_models(model_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `partition` | `varchar(10)` | no | — | — | train/validation/test/challenge split; dataset records derive it from their group. |
| `slice_key` | `varchar(120)` | no | — | — | Evaluation slice identity, such as synthetic/real/category. |
| `sample_count` | `integer` | no | — | — | Measured number of evaluated examples. |
| `fraud_count` | `integer` | no | — | — | Measured positive-label examples; equals TP + FN. |
| `true_positive` | `integer` | no | — | — | Predicted fraud and labeled fraud examples. |
| `false_positive` | `integer` | no | — | — | Predicted fraud and labeled legitimate examples. |
| `true_negative` | `integer` | no | — | — | Predicted legitimate and labeled legitimate examples. |
| `false_negative` | `integer` | no | — | — | Predicted legitimate and labeled fraud examples. |
| `average_precision` | `numeric(9,8)` | yes | — | — | Optional measured average precision in 0..1. |
| `report_key` | `text` | no | — | — | Evaluation-report artifact locator. |
| `evaluated_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
partition VARCHAR(10) NOT NULL CHECK (partition IN ('train','validation','test','challenge'))
sample_count INTEGER NOT NULL CHECK (sample_count > 0)
fraud_count INTEGER NOT NULL CHECK (fraud_count >= 0 AND fraud_count <= sample_count)
true_positive INTEGER NOT NULL CHECK (true_positive >= 0)
false_positive INTEGER NOT NULL CHECK (false_positive >= 0)
true_negative INTEGER NOT NULL CHECK (true_negative >= 0)
false_negative INTEGER NOT NULL CHECK (false_negative >= 0)
average_precision NUMERIC(9,8) CHECK (average_precision BETWEEN 0 AND 1)
UNIQUE (model_id, partition, slice_key)
CHECK (sample_count = true_positive + false_positive + true_negative + false_negative)
CHECK (fraud_count = true_positive + false_negative)
model_id BIGINT NOT NULL REFERENCES risk_models ON DELETE RESTRICT
```

## `risk_rulesets`

Versioned operating policy, feature compatibility and maximum score age.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(ruleset_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `ruleset_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `version` | `varchar(100)` | no | — | UNIQUE | Unique immutable version identity. |
| `feature_schema_id` | `bigint` | no | — | FK part → feature_schemas(feature_schema_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `state` | `varchar(10)` | no | `'draft'` | — | Configuration/dataset lifecycle state; see checks and immutability guard. |
| `max_assessment_age` | `interval` | no | `INTERVAL '24 hours'` | — | Maximum feature snapshot age for a result to remain current. |
| `created_by` | `bigint` | no | — | FK part → users(user_id) | Created by. |
| `published_by` | `bigint` | yes | — | FK part → users(user_id) | Published by. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `published_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
state VARCHAR(10) NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','active','retired'))
max_assessment_age INTERVAL NOT NULL DEFAULT INTERVAL '24 hours' CHECK (max_assessment_age > INTERVAL '0')
CHECK ((state = 'draft' AND published_at IS NULL AND published_by IS NULL) OR (state IN ('active','retired') AND published_at IS NOT NULL AND published_by IS NOT NULL))
feature_schema_id BIGINT NOT NULL REFERENCES feature_schemas ON DELETE RESTRICT
created_by BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT
published_by BIGINT REFERENCES users(user_id) ON DELETE RESTRICT
```

**Additional indexes**

```sql
CREATE UNIQUE INDEX risk_rulesets_one_active ON risk_rulesets ((TRUE)) WHERE state = 'active'
```

## `risk_rules`

Numeric rules/thresholds unique by key within their ruleset.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(rule_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `rule_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `ruleset_id` | `bigint` | no | — | FK part → risk_rulesets(ruleset_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `rule_key` | `varchar(80)` | no | — | — | Unique operating-rule key within the ruleset. |
| `numeric_value` | `numeric(14,6)` | no | — | — | Rule value; published medium/high thresholds are validated together. |
| `description` | `text` | no | — | — | Required/optional descriptive value; bounds and rules follow the SQL constraints. |

**Checks, alternate keys and foreign keys**

```sql
UNIQUE (ruleset_id, rule_key)
ruleset_id BIGINT NOT NULL REFERENCES risk_rulesets ON DELETE RESTRICT
```

## `risk_scan_jobs`

Durable at-least-once queue with pinned context/configuration and frozen features.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(job_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `job_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `product_id` | `bigint` | no | — | FK part → product_revisions(product_id, revision_no) | Stable product identity; paired with revision_no for historical content. |
| `revision_no` | `integer` | no | — | FK part → product_revisions(product_id, revision_no) | Positive revision sequence unique within a product. |
| `context_version` | `bigint` | no | — | — | Assessment evidence/refresh generation, independent of content revision. |
| `model_id` | `bigint` | yes | — | FK part → risk_models(model_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `ruleset_id` | `bigint` | yes | — | FK part → risk_rulesets(ruleset_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `feature_schema_id` | `bigint` | yes | — | FK part → feature_schemas(feature_schema_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `source_event_key` | `varchar(220)` | yes | — | UNIQUE | Stable source identity for retry/delivery deduplication. |
| `status` | `varchar(12)` | no | `'queued'` | — | Constrained workflow/account/queue state; see checks and trigger contract. |
| `attempts` | `integer` | no | `0` | — | Execution/batch attempts; scan jobs permit at most three. |
| `claim_token` | `uuid` | yes | — | — | Fresh UUID fencing token for the current processing lease. |
| `retry_at` | `timestamptz` | no | `clock_timestamp()` | — | Earliest time queued work is eligible for claim. |
| `lease_expires_at` | `timestamptz` | yes | — | — | Live processing lease expiry; expired claims cannot mutate through worker APIs. |
| `feature_as_of` | `timestamptz` | yes | — | — | Point-in-time cutoff for frozen predictor facts. |
| `feature_snapshot` | `jsonb` | yes | — | — | Write-once vector, missing indicators and reference facts reused by retries. |
| `error_code` | `varchar(80)` | yes | — | — | Sanitized machine error code; no raw traceback/private payload. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `updated_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `completed_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
context_version BIGINT NOT NULL CHECK (context_version >= 0)
status VARCHAR(12) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','succeeded','failed','superseded'))
attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3)
feature_snapshot JSONB CHECK (feature_snapshot IS NULL OR jsonb_typeof(feature_snapshot) = 'object')
FOREIGN KEY(product_id, revision_no) REFERENCES product_revisions ON DELETE RESTRICT
CHECK ((model_id IS NULL AND ruleset_id IS NULL AND feature_schema_id IS NULL) OR (model_id IS NOT NULL AND ruleset_id IS NOT NULL AND feature_schema_id IS NOT NULL))
CHECK ((feature_as_of IS NULL) = (feature_snapshot IS NULL))
CHECK (feature_snapshot IS NULL OR model_id IS NOT NULL)
CHECK ((status = 'processing' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL AND model_id IS NOT NULL) OR (status <> 'processing' AND claim_token IS NULL AND lease_expires_at IS NULL))
CHECK ((status IN ('succeeded','failed','superseded')) = (completed_at IS NOT NULL))
CHECK (status <> 'succeeded' OR feature_snapshot IS NOT NULL)
model_id BIGINT REFERENCES risk_models ON DELETE RESTRICT
ruleset_id BIGINT REFERENCES risk_rulesets ON DELETE RESTRICT
feature_schema_id BIGINT REFERENCES feature_schemas ON DELETE RESTRICT
```

## `risk_logs`

Append-only advisory prediction output, at most one per job.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(risk_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `risk_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `job_id` | `bigint` | no | — | UNIQUE; FK part → risk_scan_jobs(job_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `risk_score` | `smallint` | no | — | — | Advisory integer score in 0..100, not verified fraud probability. |
| `risk_level` | `varchar(6)` | no | — | — | low/medium/high classification under the job's pinned ruleset. |
| `observed_factors` | `jsonb` | no | `'[]'` | — | Observed warning factors, separate from causal model explanations. |
| `model_explanation` | `jsonb` | yes | — | — | Optional structured explanation; never an unsupported fraud accusation. |
| `predicted_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
risk_score SMALLINT NOT NULL CHECK (risk_score BETWEEN 0 AND 100)
risk_level VARCHAR(6) NOT NULL CHECK (risk_level IN ('low','medium','high'))
observed_factors JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(observed_factors) = 'array')
model_explanation JSONB CHECK (model_explanation IS NULL OR jsonb_typeof(model_explanation) = 'object')
job_id BIGINT NOT NULL UNIQUE REFERENCES risk_scan_jobs ON DELETE RESTRICT
```

## `risk_rescan_campaigns`

Recoverable batch-rescan obligation with immutable event scope/cutoff.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(campaign_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `campaign_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `source_event_key` | `varchar(180)` | no | — | UNIQUE | Stable source identity for retry/delivery deduplication. |
| `event_type` | `varchar(30)` | no | — | — | Configuration/evidence/daily/manual reason for a durable rescan campaign. |
| `source_audit_id` | `bigint` | yes | — | UNIQUE; FK part → admin_audit_logs(audit_id) | Required privileged source event except for the scheduled daily campaign. |
| `seller_id` | `bigint` | yes | — | FK part → users(user_id) | Owning/scoped seller identity; orders derive ownership from product. |
| `target_product_id` | `bigint` | yes | — | FK part → products(product_id) | Optional single-product campaign scope. |
| `cutoff_product_id` | `bigint` | no | — | — | Frozen maximum product ID, preventing retry scope expansion. |
| `cutoff_at` | `timestamptz` | no | `clock_timestamp()` | — | Frozen campaign creation/scope instant. |
| `refresh_date` | `date` | yes | — | — | Explicit calendar date forming a scheduled refresh event identity. |
| `refresh_timezone` | `varchar(80)` | yes | — | — | Configured timezone for deterministic daily-refresh date identity. |
| `status` | `varchar(12)` | no | `'queued'` | — | Constrained workflow/account/queue state; see checks and trigger contract. |
| `cursor_product_id` | `bigint` | no | `0` | — | Monotonic committed batch cursor. |
| `attempts` | `integer` | no | `0` | — | Execution/batch attempts; scan jobs permit at most three. |
| `error_code` | `varchar(80)` | yes | — | — | Sanitized machine error code; no raw traceback/private payload. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |
| `completed_at` | `timestamptz` | yes | — | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
event_type VARCHAR(30) NOT NULL CHECK (event_type IN ('model_activation','ruleset_publication','seller_evidence','daily_refresh','manual_rescan'))
cutoff_product_id BIGINT NOT NULL CHECK (cutoff_product_id >= 0)
status VARCHAR(12) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','completed','failed'))
cursor_product_id BIGINT NOT NULL DEFAULT 0 CHECK (cursor_product_id >= 0)
attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0)
CHECK (cursor_product_id <= cutoff_product_id)
CHECK ((refresh_date IS NULL) = (refresh_timezone IS NULL))
CHECK ((event_type = 'daily_refresh') = (refresh_date IS NOT NULL AND refresh_timezone IS NOT NULL))
CHECK (event_type = 'daily_refresh' OR source_audit_id IS NOT NULL)
CHECK ((status = 'completed') = (completed_at IS NOT NULL))
source_audit_id BIGINT UNIQUE REFERENCES admin_audit_logs ON DELETE RESTRICT
seller_id BIGINT REFERENCES users(user_id) ON DELETE RESTRICT
target_product_id BIGINT REFERENCES products(product_id) ON DELETE RESTRICT
```

## `risk_rescan_events`

Durable campaign/product delivery receipt preserving deduplication.

**Source:** [002_risk.sql](../../database/002_risk.sql) · **Primary key:** `(campaign_id, product_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `campaign_id` | `bigint` | no | — | PK; FK part → risk_rescan_campaigns(campaign_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `product_id` | `bigint` | no | — | PK; FK part → products(product_id) | Stable product identity; paired with revision_no for historical content. |
| `job_id` | `bigint` | no | — | FK part → risk_scan_jobs(job_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
PRIMARY KEY(campaign_id, product_id)
campaign_id BIGINT NOT NULL REFERENCES risk_rescan_campaigns ON DELETE RESTRICT
product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT
job_id BIGINT NOT NULL REFERENCES risk_scan_jobs ON DELETE RESTRICT
```

## `embedding_models`

P2 immutable embedding model/version/dimensionality metadata.

**Source:** [007_embeddings_optional.sql](../../database/007_embeddings_optional.sql) · **Primary key:** `(embedding_model_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `embedding_model_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `version` | `varchar(120)` | no | — | UNIQUE | Unique immutable version identity. |
| `model_name` | `text` | no | — | — | Model name. |
| `model_revision` | `text` | no | — | — | Model revision. |
| `dimensions` | `integer` | no | `384` | — | Dimensions. |
| `text_policy` | `text` | no | — | — | Text policy. |
| `dependency_manifest` | `jsonb` | no | — | — | Exact training/inference package versions as structured metadata. |
| `registered_by` | `bigint` | no | — | FK part → users(user_id) | Registered by. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
dimensions INTEGER NOT NULL DEFAULT 384 CHECK (dimensions=384)
dependency_manifest JSONB NOT NULL CHECK (jsonb_typeof(dependency_manifest)='object')
registered_by BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT
```

## `review_embedding`

P2 review vectors linked to exact review/model and source fingerprint.

**Source:** [007_embeddings_optional.sql](../../database/007_embeddings_optional.sql) · **Primary key:** `(review_embedding_id)`

| Column | SQL type | Null? | Default | Key/reference | Purpose |
| --- | --- | --- | --- | --- | --- |
| `review_embedding_id` | `bigint` | no | `identity` | PK | Relational identifier; primary/foreign key role is shown alongside. |
| `review_id` | `bigint` | no | — | FK part → moderation_reviews(review_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `embedding_model_id` | `bigint` | no | — | FK part → embedding_models(embedding_model_id) | Relational identifier; primary/foreign key role is shown alongside. |
| `content_sha256` | `char(64)` | no | — | — | SHA-256 of the stored file contents. |
| `embedding` | `vector(384)` | no | — | — | Embedding. |
| `created_at` | `timestamptz` | no | `clock_timestamp()` | — | Recorded lifecycle instant; timestamptz stores an absolute point in time. |

**Checks, alternate keys and foreign keys**

```sql
content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$')
embedding VECTOR(384) NOT NULL CHECK (vector_norm(embedding)>0)
UNIQUE(review_id, embedding_model_id)
review_id BIGINT NOT NULL REFERENCES moderation_reviews(review_id) ON DELETE RESTRICT
embedding_model_id BIGINT NOT NULL REFERENCES embedding_models ON DELETE RESTRICT
```
