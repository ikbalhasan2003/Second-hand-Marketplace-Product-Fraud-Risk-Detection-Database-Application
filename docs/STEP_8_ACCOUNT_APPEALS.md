# Step 8 ? Account appeals and restrictions (2026-11-07)

Blocked buyer and seller accounts retain authentication because marketplace `status` is separate from authentication `is_active`. The email backend intentionally continues to reject authentication-disabled accounts. Existing sessions reload the user each request. Blocked marketplace sign-ins now default to `/account/appeals/`; safe explicit return paths retain existing behavior. Administrator sign-in still requires active status.

## Workflow and privacy

`/account/appeals/` is authenticated, owner-scoped and available without active marketplace status. Submission requires current database status blocked and authentication enabled. Reasons contain 10?5000 characters, with up to three optional decoded JPEG/PNG/WebP images of at most 5 MiB each. Existing image validation strips metadata, verifies actual format, bounds dimensions and rejects animated/invalid files. Storage uses randomized keys under PRIVATE_MEDIA_ROOT, never the public media root. Failed submissions remove newly written files and roll back records. The account page links to appeal history and decisions.

SQL-owned account_appeals and account_appeal_evidence tables follow the existing marketplace migration architecture. An account lock and partial unique index allow one pending/reviewing appeal per account, including concurrent submissions. Rejected accounts may submit another appeal with additional information. No automatic unblock occurs on submission. Pending can become reviewing, approved or rejected; reviewing can become approved or rejected. Terminal decisions cannot be edited or deleted. Evidence is immutable.

`/admin-app/appeals/` presents open appeals first, with pagination, private evidence links, reasons and decision notes. An active administrator chooses Under Review, Approve and unblock, or Reject, with required notes. Stale expected states reject overwrites. The database stamps reviewer identity and review time, and writes the appeal decision audit and approved account status audit in the same transaction. Approval explicitly changes blocked to active; rejection leaves account status unchanged. Approval fails if another action already unblocked the account. Audit/transaction failures roll back both changes. Admin account moderation remains separately available and audited.

`/account/appeals/evidence/<id>/` allows only the owner or an active administrator, verifies stored hash/length, serves downloads with nosniff, and prevents caching. Other participants, including sellers of reported products, have no appeal evidence access. Pages and decisions use private/no-store caching and CSRF-protected forms. Status and decision notes are delivered through the owner?s appeal history; this step adds no email transport.

## Restriction policy

Blocked accounts can read their own marketplace history, manage account credentials/profile, submit/view appeals, and fulfil existing order obligations under the established Step 6 order transition policy. Existing open fraud cases retain their evidence follow-up route. These are narrow existing-account capabilities; blocked users cannot gain memberships, create/edit/publish/withdraw listings, upload listing images, send chat messages, open new conversations, file new marketplace reports or place purchases. Evidence uploads for appeals and existing open reports are explicit exceptions.

Public catalog and listing-media access exclude blocked sellers. Blocking preserves listing visibility/revisions rather than rewriting or deleting historical records. Unblocking makes otherwise eligible listings discoverable again, subject to current assessment/publication and visibility controls; administrator-removed listings remain removed. Existing orders, reservations, immutable purchase terms and assessments are retained. Participant obligations, cancellation/dispute rules and expiry processing remain in effect; blocking does not fabricate cancellation/completion or release reservations.

Existing handlers, listing services and SQL triggers already enforce active membership for marketplace creation and chat sends. Purchase service now checks current database account state even for a stale in-memory user or idempotent request. SQL purchase validation remains the atomic authority for both buyer and seller eligibility. Restricted secondhand_web grants cover the new tables/sequences and the audit trigger executes with a fixed search path; no direct audit insert grant is added.

## Migration and recovery

Created custom-format backup `.local/backups/step8-before-account-appeals.dump` (540211 bytes) before applying marketplace.0009_account_appeals to the configured working database. The additive migration applied successfully. No working user statuses, listings or orders were backfilled or deleted. The migration is forward-only; recover the previous schema/data using the backup in a separate recovery database and reconcile subsequent writes before replacement. Keep PRIVATE_MEDIA_ROOT backed up separately; database archives do not contain uploaded evidence.

## Verification

Initial appeal tests: 2 passed. Expanded appeals/accounts/seller/buyer/evidence/admin suite: 79 passed in 32.52 seconds. Added existing-session/stale-principal restriction coverage, then buyer/appeal suite: 24 passed in 7.68 seconds. Tests verify owner/admin evidence privacy, public-path denial, invalid-image rollback, duplicate controls, seller sign-in, approve/reject/review/stale transitions, immutable history, decision/unblock/audit rollback, real restricted database role execution, hidden blocked-seller listings, blocked uploads/sends/purchases and retained order obligations. Django system checks, migration consistency and targeted Ruff checks passed. Full-suite result follows below. No interactive browser review was performed.


Full repository suite: **122 passed in 131.92 seconds**. After the final blocked-login destination and direct SQL self-approval/terminal-history test additions, the appeal/account regression run passed **19 tests in 8.54 seconds** and targeted Ruff passed again. An attempted overlapping test invocation encountered the shared disposable test database already in use; it was rerun successfully after the full suite completed. No working database was targeted by tests.
