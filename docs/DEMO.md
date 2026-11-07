# Buyer, Seller and Admin demonstration

Use the [Windows setup](SETUP.md), [account setup](ACCOUNTS.md), [migration authority](MIGRATIONS.md) and [ML instructions](ML_PIPELINE.md). The demo uses synthetic records and agreements only. No payment gateway, external messaging broker or paid model API is required.

## Prepare the environment

1. Apply Django migrations to a fresh PostgreSQL application database using the migration credential. Apply process privileges according to the deployment instructions, then run the web process with the web login.
2. Register a seller through `/register/?role=seller` and two buyers through `/register/`, using distinct synthetic `.invalid` emails. Keep Buyer One and Buyer Two in different browser profiles so their sessions are independent. Existing identities enable the other marketplace role explicitly from Account.
3. Provision a separate administrator with the trusted management command documented in [ACCOUNTS.md](ACCOUNTS.md). Public registration never provisions an administrator. Do not use the standalone SQL seed as live credentials: its `!` passwords cannot authenticate.
4. Generate/train/register the actual synthetic dataset/model following [ML_PIPELINE.md](ML_PIPELINE.md), or leave the model unregistered to demonstrate pending risk honestly. Registration and activation are separate controlled actions. The fitted pipeline/artifact roots must match the worker process's configuration.

## Cross-application workflow

1. As Seller, open `/sell/`, create a listing and save only a title as a private draft. Confirm there is no public content or completed score. Add a description, category, positive USD price, condition and location; upload a small JPEG/PNG/WebP image. Publish. The receipt identifies immutable revision r1 and a durable queued scan.
2. Keep the worker stopped. As Seller, inspect the submitted listing and its pending assessment in `/sell/`. As Buyer One, verify it is absent from search and its direct URL is unavailable. Start the configured worker with a compatible active model; only a successful current scan enables public listing access. Risk absence never means zero risk.
3. Activate a compatible trusted model/ruleset as Admin, run the scan worker and maintenance campaign processing, then refresh the listing. Show its actual observed factors, timestamps and current state. The synthetic-only model output is advisory; do not invent a desired score for the demonstration.
4. As Buyer One, start a conversation and send a question. As Seller, open Buyer conversations and reply. Load the thread in Buyer Two's session by copying the URL; access is denied. Demonstrate read receipts only for messages actually viewed by the receiving participant.
5. Before ordering, publish a legitimate edit as r2. Show Seller revision history retaining r1. As Buyer One, review r2 and place an order. Repeat the same submitted request key in the automated test rather than manually making a second agreement: it returns the original order. The independent database regression demonstrates a competing-buyer race.
6. As Seller, show the reserved listing and disabled material editing. Accept the order and mark it shipped; as Buyer One, confirm receipt. Show the shared timeline and immutable purchased revision. An in-person handover instead permits Buyer completion from Accepted. No screen verifies external payment or shipping.
7. As Buyer One, submit an order-linked concern with a private evidence image. Show the purchased revision and report status. Buyer Two and the reported seller cannot retrieve the evidence URL. A blocked/deactivated reporter can still add evidence to their own open case and complete authorized existing-order obligations; new trading/chat is restricted.
8. As Admin, open the deduplicated review queue and case workspace. Distinguish a user allegation, model score and human verdict. Record an evidence-backed decision with a reason; show its audit receipt. Append an Unresolved correction referencing the prior decision and confirm that the older label is excluded from future eligible exports.
9. Demonstrate listing/account moderation as separate reasoned administrator actions. Blocking or removal never occurs solely because the model score is high. Show that cancellation cannot restore administrator-removed visibility and that completed goods cannot sell again.
10. Inspect model/rules history. On Admin Overview, request an audited rescan using a published listing ID and a reason, or activate a compatible version on Models and rules. On an open report, demonstrate Assign to me/Reassign and its audit receipt. Existing predictions become outdated until reassessment; campaign progress comes from persisted database state. Open the read-only audit browser and administrator-only dataset export workflow.

## Recovery and limitations

Run the [delivery verifier](DELIVERY.md) on a disposable local PostgreSQL server to reproduce the performance workload and coordinated database/media/artifact restore. It creates new isolated databases and retains the recovery set for inspection. The script verifies actual file checksums, order/revision/result links and private-evidence access through restricted HTTP requests.

The automated suites and measured evidence are linked in [DELIVERY.md](DELIVERY.md). Manual keyboard/mobile/browser observations are separate acceptance evidence; do not present an unperformed manual check as passed. Dataset performance is synthetic only. Real payments, identity verification, external notifications, online learning and image forgery detection remain outside P0.

## Delivery rehearsal evidence

`tests/integration/test_delivery.py::test_cross_application_publish_chat_fulfil_report_review` executes one continuous HTTP scenario with three independent authenticated sessions: Seller publication; pending listing exclusion, real fitted inference, then Buyer discovery; two-way private chat; purchase; Seller acceptance/shipping; Buyer completion; order-linked private evidence; Admin decision and report resolution; and the Buyer's resulting public-facing outcome. It verifies that fulfilment state agrees across both marketplace applications and that evidence remains unavailable to the seller. Worker recovery and scored inference are exercised separately by the real-worker suite and delivery verifier.

This automated rehearsal passed locally. It is not a recording of a human operating three browser profiles. For presentation sign-off, retain the independent profiles above, tab through navigation/forms, open and dismiss order review with Enter/Escape, inspect the real pending/ready assessment and its timestamps, and resize to 360px. Verify focus restoration, scrollable tables, restriction feedback and unsent-draft recovery. Do not force a particular model score to make the demonstration look successful.

## Update rehearsal additions

Use [the operating guide](OPERATIONS.md) for current policy. In separate synthetic sessions, demonstrate a blocked member submitting private evidence at `/account/appeals/`, admin review at `/admin-app/appeals/`, and an explicit audited unblock. Show the new user/product directories, risk history and timeout policy. Export an authorized frozen dataset as CSV and inspect provenance/formula escaping; use JSONL ZIP for fitting. Freezing a dataset queues training; start `run_training_worker` (or `start_demo.ps1 -WithWorker -WithTrainingWorker`) and display actual job progress/failure. A successful candidate still needs explicit audited activation. Do not freeze real data or replace a working model merely for a presentation. Synthetic evaluation never demonstrates real-world fraud accuracy.
