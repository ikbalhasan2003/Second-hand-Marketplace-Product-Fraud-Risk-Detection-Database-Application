# P0 configuration decisions

Decision date: 4 November 2026. These defaults resolve the open design decisions in the PRD and architecture. This file records the required policy; a decision is not evidence that its application enforcement or acceptance test has passed. Consult the delivery verification record for measured implementation status.

## Configuration authority

Keep secrets and machine-specific paths in environment configuration. Keep shared financial/order policy in the existing `marketplace_settings` singleton. Keep feature semantics in an immutable `feature_schemas` version and risk thresholds/freshness in a compatible versioned ruleset. Environment changes must not silently alter a registered feature contract or existing revision prices.

| Setting | P0 default | Authority and validation |
| --- | --- | --- |
| Currency | `USD` | `marketplace_settings.currency`; three uppercase ASCII letters. Set before the first revision; the existing SQL guard prevents subsequent change. Display the stored revision currency. No exchange-rate conversion. |
| Supported interface/listing language | English (`en`) | Deployment setting. Unicode text remains accepted, but the v1 phrase dictionary and evaluation support English only. Do not claim multilingual detection. |
| Display/refresh timezone | `Asia/Shanghai` | Django display setting and `marketplace_settings.refresh_timezone`; all persisted instants remain timezone aware. Daily campaigns use an explicit local date and timezone. |
| Demo locations | Shanghai, Beijing, Guangzhou, Shenzhen, Hangzhou | Configurable suggestions for synthetic generation/forms; also accept nonempty free text up to the SQL limit of 150 characters. Suggestions neither verify geography nor imply a real deployment market. Legacy SQL fixtures use `Demo City`. |
| Listing images | At most 6; each 1–5,242,880 bytes (5 MiB) | Deployment limits may be tightened, never exceed existing SQL bounds without a reviewed schema change. Zero images are allowed. |
| Report evidence | At most 3; same per-file size/type limits | Private storage, participant/administrator authorization and immutable generated keys. |
| Image formats | JPEG, PNG, WebP | Decode with Pillow; extension or browser MIME alone is insufficient. Reject malformed, animated, executable and SVG content; do not trust embedded metadata. |
| Decoded image dimensions | Maximum 40,000,000 pixels; positive width/height | Reject decompression bombs before storing. No minimum resolution that would reject valid small course fixtures. |
| Total upload request | 33,554,432 bytes (32 MiB) | Bound declared length and actual streamed file bytes in Django, non-file form bytes in Django, and complete multipart body at the deployment proxy. At most 6 files per request, with each workflow's stricter count. |
| Listing fields | Title 200; description 20,000; location 150 characters | Trim required text and enforce existing SQL limits. Price is positive, finite, at most `9,999,999,999.99`, with two decimal places; original price is optional and nonnegative. |
| Chat/report fields | Message 4,000; report description 5,000 characters | Nonempty after trimming; escaped on display. |
| Evidence/history retention | Indefinite during the course demonstration (`0` retention days) | Retain revisions, referenced files, orders, decisions, results and audit records. No P0 automatic evidence deletion. A positive future policy requires a designed reference-aware purge/anonymization workflow; merely setting a number must not erase history. |
| Deactivated-account access | Preserve existing obligations | The fixed policy below applies. Configuration cannot grant new trading privileges to restricted accounts. |
| Unanswered order expiry | 48 hours | Existing database setting and `expire_unanswered_orders`; applies only to `placed` orders. |
| Current assessment age | 24 hours | Versioned `risk_rulesets.max_assessment_age`; currentness also requires matching revision/context/model/ruleset/schema. |
| Risk thresholds | Medium starts at 40; High at 75 | Published versioned rules; `0 <= medium_min < high_min <= 100`. |
| Pagination / polling | Catalog 12 cards; dashboard/history 20 rows; chat/risk poll every 5 seconds | Bounded page size and stable ID tiebreaker. Pause overlapping polling and back off on failure. |
| Worker | 120-second lease; heartbeat at most 30 seconds; idle poll 2 seconds | SQL permits positive leases at most 10 minutes. Keep inference outside long-held transactions. |
| Maintenance | Batch 100; daily reassessment; expire orders every 5 minutes | External scheduler; durable campaigns and idempotent database functions. Retry attempts/backoff remain the existing SQL policy: at most 3 claims and retry delay `2^attempts` seconds. |

## Rate limits

Use shared counters across processes. Apply limits before the protected mutation, including login failures; return HTTP 429 with a retry interval. Counts use fixed windows of the stated length and an atomic increment. A successful request does not reset an attacker's counter. Hash normalized email/IP counter keys and never log passwords or raw credentials. Trust forwarded client IP headers only behind an explicitly configured trusted proxy.

| Action | Default limit | Counter scope |
| --- | --- | --- |
| Login | 10 attempts / 15 minutes per scope | Client IP and normalized email; both must permit the request |
| Registration | 5 / hour | Client IP |
| Listing creation/edit/publication | 20 / hour | Authenticated member, shared across the Seller App |
| Chat send | 30 / minute | Authenticated member, shared across conversations |
| New fraud report | 5 / hour | Authenticated member |

These are demonstration abuse controls, not measured capacity limits. Tightening a limit is operational configuration; disabling shared enforcement in a deployment would leave the associated PRD requirement unmet.

## Account status and session policy

`status` and `is_active` have separate purposes. `is_active=false` disables authentication and invalidates access. `blocked` or `deactivated` with `is_active=true` can authenticate to a restricted account workspace. Password change and logout use Django APIs; password changes rotate the session authentication hash, invalidating other sessions. Administrator accounts additionally require active status and separate administrator membership.

| Capability | Active member | Blocked/deactivated member |
| --- | --- | --- |
| Read own orders, revisions, conversations and report status | Yes, with ownership and role checks | Yes, with the same checks |
| Access reporter's own private evidence | Yes | Yes |
| Act on an existing order | Role/state-appropriate fulfilment, cancellation or dispute | Same existing obligations; no new order |
| Add evidence to the reporter's existing open case | Yes, within limits | Yes, within limits |
| Publish/edit/withdraw listings; place an order; start/send chat; create a report; enable a role | Yes, if authorized | No |
| Resolve disputes or perform administrator mutations | Separately provisioned active administrator only | No |

Deactivation is soft and does not remove memberships or referenced evidence. Reactivation is a controlled administrative action with a reason/audit trail; there is no self-service bypass of a block. Do not blanket-redirect restricted members away from existing-order obligations. A disabled-authentication account requires trusted administrator assistance instead.

## Implementation boundaries

The reference SQL already implements the currency/timeout/timezone defaults, upload metadata bounds, immutable history, status values, transactional order transitions, queue leases/retries and risk currentness. It does not decode image bytes, configure Django sessions/CSRF, enforce browser-user object access, or implement shared rate counters. Those remain application responsibilities until implemented and verified. P1 appeals/notifications and P2 embeddings remain outside this decision set.

The immutable feature contract is [FEATURE_CONTRACT.md](FEATURE_CONTRACT.md). An override to its normalization, windows, predictors or missing-value policy requires a new schema version and compatible retraining, rather than an environment toggle.
