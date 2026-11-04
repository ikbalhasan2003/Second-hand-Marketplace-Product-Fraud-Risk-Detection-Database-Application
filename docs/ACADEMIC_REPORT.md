# Second-hand marketplace and product fraud risk screening

## Project scope

The project implements a database-centered second-hand marketplace with separate Buyer, Seller and Admin applications sharing one Django backend and PostgreSQL database. Its P0 contribution is the integration of immutable marketplace evidence, transactional orders, private reporting, accountable moderation and reproducible machine-learning screening. Scores prioritize review; a score alone cannot establish fraud, block an account or remove a listing.

The baseline uses Python 3.13, Django 5.2 LTS, PostgreSQL 18, local Bootstrap/templates, Psycopg 3 and scikit-learn. Exact installed versions are pinned in `requirements/lock.txt` and recorded with each actual fitted artifact. Orders are purchase agreements; payments and external fulfilment verification are outside the system. Appeals/notifications are P1, while embeddings, image similarity and advanced language models remain P2.

## Relational design and integrity

The operational schema separates shared identities and explicit role memberships, products and immutable revisions, purchase agreements and transition history, conversations and messages, allegations and evidence, canonical human decisions, technical model provenance and scan execution. The ER diagrams, relational schema and data dictionary are generated from the reference SQL and linked in [DATABASE_DESIGN.md](../DATABASE_DESIGN.md).

Revision identity is `(product_id, revision_no)`. Orders and reports retain that exact composite target rather than substituting today's content. A deferrable current-revision reference allows a publication transaction to create complete content/images and advance the product pointer atomically. Image associations can be inserted only in the revision's creation transaction, and historical rows cannot be overwritten. Files use generated immutable keys and checksums; relational constraints alone cannot protect bytes on disk.

Operational facts follow the documented 3NF design, with deliberate technical exceptions. A scan job freezes feature evidence and bound schema/model/ruleset context; dataset records freeze exported vectors and lineage. These historical JSON snapshots preserve an observation rather than becoming editable profiles or a substitute for relational relationships. Persisted compatibility declarations and risk level are controlled denormalization, not a claim that every physical column is independent in strict 3NF.

The partial unique order index permits at most one non-cancelled agreement per product, including after completion. The placement function locks participants and product, validates visible/available status and immutable purchase revision, and creates reservation/history together. Buyer-scoped idempotency keys replay identical facts and reject different facts. State transitions serialize actor checks, availability changes and history; cancellation never overrides an administrator removal. Independent database connections exercise a competing purchase race.

Canonical moderation decisions form an append-only chain per revision. Corrections reference the immediate predecessor, preventing competing branches. Training eligibility selects the latest decision first, then accepts only evidence-backed Fraud/Legitimate. An Unresolved successor excludes an earlier label. Required privileged audit writes share the mutation transaction; forced audit failure must roll back the action.

## Application and privacy boundaries

One email-login identity can explicitly hold Buyer and Seller memberships. Signing in or changing applications never grants a role. Separately provisioned administrator identities do not trade in P0. Django bcrypt password/session APIs, CSRF checks and server-side role/ownership checks govern browser requests. Database process roles separately restrict web, worker, maintenance and training capabilities; backend actor context is a trusted assertion, not browser-controlled database authentication.

Availability and visibility are independent. Private incomplete draft storage does not modify a public immutable revision. Active orders/completed sales prevent material editing. Blocked/deactivated members retain authorized own history, open-case evidence and existing-order obligations; new listing/trading/chat/role actions are restricted. Disabling authentication is a separate `is_active` action.

Image uploads are bounded and decoded as supported single-frame images. Uploaded names/MIME claims do not determine storage type. Public listing files and private evidence have separate roots. Evidence is returned through reporter/administrator authorization with private caching; it is not automatically shared with the reported seller. P0 model inputs exclude private conversations, contact details, raw attachments and account-block decisions.

## Feature extraction, learning and reproducibility

[FEATURE_CONTRACT.md](FEATURE_CONTRACT.md) freezes `marketplace-v1`: price ratio/reference count/missing flag; distinct suspicious phrase count; seller age; prior confirmed fraud count; seven-day publication frequency; image count; location difference/missing flag; and thirty-day duplicate-text count. References use one latest eligible revision per earlier comparable product in the same category/condition/currency within ninety days, with a minimum of fifteen. Unicode normalization and phrase boundaries are versioned. Missing evidence remains explicit.

The worker extracts a consistent repeatable-read snapshot at a recorded cutoff. It excludes future evidence, selects canonical decisions as known then, and freezes observed mutable profile location. Retries reuse that snapshot. Historical exports require an existing provable point-in-time vector; current mutable state cannot replace missing history.

The actual project generator creates 5,000 synthetic scenarios with seed `20261104`, provenance, source notes, timestamps, grouping keys and labels explicitly marked simulated. Connected seller/template/duplicate groups stay together in train/validation/test partitions. Fitted imputation and Logistic Regression scaling use training records only. Random Forest, Logistic Regression and transparent rules are evaluated on identical frozen partitions at a fixed threshold. No real dataset or independently authored challenge set is claimed.

The saved Random Forest artifact contains fitted preprocessing and classification. Its immutable manifest records SHA-256, dependency versions, feature schema/order/hash, class mapping, dataset checksum/split policy, seed, source code revision, actual evaluation report and limitations. Trusted operator registration validates project-produced artifacts; activation remains a separate audited administrator action. A checksum detects changed bytes but does not make arbitrary uploaded pickle content safe.

Measured metrics and confusion matrices are retained in the evaluation artifact and summarized in delivery evidence. Random Forest's initial selection is a design choice, not a guaranteed best-model claim. Precision, recall, F1 and average precision describe the simulated holdout only; no real-world fraud accuracy, calibration, identity verification or causal explanation is established.

The actual 5,000-record run used 3,480 training, 760 validation and 760 test records. Its untouched synthetic test partition contains 185 Fraud and 575 Legitimate labels. The fixed 0.5 classification threshold produced:

| Method | Precision | Recall | F1 | Average precision | TN / FP / FN / TP |
| --- | --- | --- | --- | --- | --- |
| Rules | 0.6054 | 0.4811 | 0.5361 | 0.5149 | 517 / 58 / 96 / 89 |
| Logistic Regression | 0.5602 | 0.8054 | 0.6608 | 0.6068 | 458 / 117 / 36 / 149 |
| Random Forest | 0.5882 | 0.7568 | 0.6619 | 0.5559 | 477 / 98 / 45 / 140 |

Random Forest's F1 is close to Logistic Regression's; Logistic Regression has higher average precision and recall in this simulated holdout. The baseline choice therefore does not establish Random Forest superiority. The 98 Random Forest false positives demonstrate why scores cannot automatically impose penalties. There are no real-source rows, and no real-source performance measurement. The immutable dataset SHA-256 is `7038f56947f8a07f9dc9e501aff19851cf40190a2c286f648fe9c5c9735fc959`; the fitted Random Forest SHA-256 is `727e9b7c6346295ae8e9bdfb87fe35aba395935691d6394a0647aa3221aef2bb`.

## Durable risk execution

PostgreSQL stores durable jobs and rescan campaigns. Publication can commit while the worker is stopped. Short claims use `FOR UPDATE SKIP LOCKED`, a lease and fresh fencing token. Feature work/inference happen outside the claim transaction, with heartbeat renewal. Claim-checked completion atomically records one result and success; expired workers cannot finalize after replacement. Bounded retry/backoff and terminal failures remain explicit.

A current score requires matching content revision, assessment context, active model/ruleset, feature schema, completed job and snapshot maximum age. Historical results remain preserved. Pending, scanning, stale and failed states have no current numeric score, and only current completed Low results qualify for the Low filter. Configuration/evidence changes create recoverable rescan obligations rather than synchronous bulk inference.

## Verification and measured limitations

[DELIVERY.md](DELIVERY.md) maps AC-01–AC-23 to executed application/database/worker/model tests and records the precise performance/recovery methodology. [evidence/delivery.json](evidence/delivery.json) contains machine-recorded run identifiers, environment, durations, checks and failures. The search target uses 10,000 listings and ten concurrent clients; scan latency uses one warm worker and twenty waiting jobs. A coordinated restore covers the database, actual media and trusted artifacts, then verifies ownership through the restricted web role.

Automated integration does not replace a recorded full manual multi-browser demonstration or keyboard/mobile inspection. The measured performance workload excludes network/TLS/image transfer and runs on one local host. The restore drill is quiesced and isolated, not online point-in-time recovery. Evidence retention is indefinite for the synthetic course demonstration; collecting real participant evidence would require a separately designed retention/erasure policy.

The defensible result is a functioning risk-screening prototype evaluated against synthetic marketplace scenarios and PostgreSQL integrity/security/recovery checks. Further research requires representative real outcomes, external validation and unseen-domain evaluation before making deployment-effectiveness claims.
