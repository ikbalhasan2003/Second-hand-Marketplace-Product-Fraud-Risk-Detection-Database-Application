# Low-fidelity UI wireframe specification

## Scope and conventions

**Project:** Second-hand Marketplace & Product Fraud Risk Detection, PRD v2.1.  
**Deliverable:** Text-only, black-and-white wireframe reference for Figma or Draw.io; 17 page specifications and shared component states. No images, rendered mockups or production color styling.

**Source of requirements:** [PRD](../PRD.md), [Architecture](../ARCHITECTURE.md), [Technical stack](../TECH_STACK.md), [Database package](../database/README.md) and its reference SQL. These are design specifications, not a claim that application pages or a trained model already exist.

- Keep three application shells: Buyer `/buyer-app/`, Seller `/seller-app/`, Admin `/admin-app/`. They share identity, services and one PostgreSQL database. Switching apps never grants a role.
- Preserve the architecture's proposed routes where given. Additional GET page/detail routes below are proposed wireframe contracts to finalize in Django URL configuration. Use ordinary ASCII hyphens in URLs.
- Desktop reference frame: 1440 px wide, 12-column grid, consistent page margins. Mobile reference: 360 px wide, one column. Dimensions are layout guides, not fixed viewport requirements.
- Draw white surfaces, black text, simple outlines, dividers and patterned/outlined status markers. Use crossed rectangles labelled `[IMAGE PLACEHOLDER]`; never include real photos. Distinguish button importance through border weight and placement.
- Reading order in every layout is top to bottom, then left to right. `[Button]` means an action; `Text link` means navigation; `[Select v]`, `[ ]` and `( )` denote form controls. Show field labels outside inputs.
- Buyer navigation: Browse, My orders, Messages, My reports, Account. Seller navigation: Dashboard, Listings, Sales, Messages, Account. Admin navigation: Overview, Review queue, Models & rules, Audit log, Export dataset. Show role switching only for memberships already held; an explicit account action enables an additional marketplace role.
- Show the configured currency code with all prices; the reference database seeds USD, while deployment currency must be chosen before revisions exist. Use absolute date/time with timezone for assessments, orders, receipts and audits; relative time may supplement it.
- Treat availability (`draft`, `available`, `reserved`, `sold`), visibility (`visible`, `removed_by_seller`, `removed_by_admin`), assessment state and moderation verdict as separate facts.
- All sample product names, prices, scores and timestamps in a future wireframe must be marked illustrative. No invented live metrics or model performance.

## Shared components and interaction rules

### G1. Risk badge, assessment panel and status mapping

**Badge anatomy:** `[outlined symbol | explicit status text]`, with a short supporting line when space allows. Accessible name includes the complete text. Low/Medium/High never use a checkmark implying verified safety.

The request names five badge variants but also requires Unassessed. Retain all five and add a neutral fallback; never merge Unassessed into Low risk. Pending and scanning share a visual family but have different text. Failed and Unassessed remain distinguishable.

| Variant / semantic case | Monochrome wireframe label | Supporting treatment |
| --- | --- | --- |
| Low, current result | `[circle · Low risk]` | `AI risk indicator; not a guarantee of safety.` |
| Medium, current result | `[triangle ! · Medium risk]` | Caution box and observed factors. |
| High, current result | `[triangle !! · High risk]` | Double-outline caution box; ordering warning G4. No automatic removal/blocking. |
| Pending/scanning | `[hourglass · Scan pending]` or `[hourglass · Scanning]` | `Queued for assessment` / `Assessment in progress`; no score or fake progress percentage. |
| Failed | `[cross · Scan failed]` | `Assessment unavailable. Risk has not been established.` Sanitized retry guidance. |
| Neutral fallback: unassessed/stale | `[dash · Unassessed]` | For stale history add `Previous assessment outdated`; otherwise `No current assessment available`. |

**Color annotation only:** PRD production styles associate Low with green, Medium with orange and High with red. Keep every wireframe black and white; the labels and symbols must work without these colors.

**Backend-to-UI contract:**

| Backend assessment state | Primary public UI | Numeric current score |
| --- | --- | --- |
| `ready`, `risk_level=low/medium/high` | Corresponding Low/Medium/High badge | Supplied current score, if displayed, as `Risk score: n/100` |
| `pending` | Scan pending; configuration unavailable may use `Assessment waiting` | None |
| `scanning` | Scanning, only for a live processing lease | None |
| `failed` | Scan failed, terminal attempt with no runnable successor | None |
| `stale` | Unassessed + Previous assessment outdated | None |
| No previous assessment and no job | Unassessed + Awaiting assessment; backend treats as pending and alerts operators | None |

Use the server-derived current state. A current successful result takes precedence; otherwise show running work, queued/retry work, terminal failure or stale history in the architecture's order. An expired processing lease becomes pending recovery. A previous score may appear only inside a clearly labelled historical section tied to its own revision/time.

Currentness requires matching product revision, context, active model, active ruleset, successful job and compatible feature schema; feature snapshot age initially must not exceed 24 hours. Never select a badge merely by the latest completion timestamp. The Unassessed browse filter includes every non-`ready` state; Low/Medium/High filters include only current `ready` results of that level.

**Assessment detail anatomy:** badge; exact `Assessed revision rN`; `Assessed at [timestamp + timezone]`; `Features as of [timestamp + timezone]`; model/ruleset references in a disclosure panel; observed warning factors; permanent advisory text: `AI risk is an indicator, not a fraud verdict. Check the listing and seller before agreeing to buy.`

Display only observed factors supplied for that assessment, such as `Price far below category median`. Do not invent a factor when the comparison baseline is missing. `No warning factors returned` does not mean safe. Global model feature importance must not be presented as a local explanation or proof of fraud. Do not label the score a verified probability of fraud.

**Mapping:** LIST-08; PRD §4.4; SCAN-02, SCAN-06–09; AC-04, AC-08.

### G2. Account restriction banner and access gates

Place a persistent, full-width outlined banner below each app header for a blocked account: `[! Account restricted] You cannot create or publish listings, send messages or place orders. You can view your history and manage existing order obligations.` Include the permitted moderation notice/reason link and logout.

- Treat the requested banner overlay as a persistent page layer, not a modal that traps the user or obscures order history. Do not rely on a dismissible toast alone.
- Disable new-listing creation, draft-save/edit/publish, new-order and message-send controls with adjacent explanatory text. Block the same requests on the server. Existing chats remain readable.
- Preserve authorized fulfilment, cancellation, receipt confirmation, disputes and evidence handling for existing orders, subject to the state machine. Do not use a blanket account lock to hide these obligations.
- Allow permitted report/evidence access according to the server policy. Blocked status alone must not hide the evidence workflow for an existing order. Seller appeals are P1 and must not appear as a working P0 button.
- Apply the component to every authenticated shell where the account can legitimately sign in. A restricted administrator cannot perform privileged mutations; shared membership/status checks remain authoritative.
- For missing role: show `Buyer access required` or `Seller access required`, with sign-in or explicit authenticated role enablement where allowed. Never enable a role just by following a URL. Admin has no public registration.
- For private objects, use a generic unavailable/not-found screen where disclosing existence would leak another person's information. Deactivated-account history/obligation permissions remain an architecture open decision; do not silently equate them with active or blocked policy.

**Mapping:** AUTH-03–06; ORDER-07; CHAT-04; PRD §2; Architecture §10.1.

### G3. Listing snapshot, order timeline and conflict treatment

**RevisionReference:** `Listing #ID · Revision rN`, an immutable snapshot link, price with currency, title, and revision creation time. Labels distinguish `Current listing revision`, `Ordered revision`, `Reported revision` and `Assessed revision`. Store/submit the expected `(product_id, revision_no)` through server validation; never silently substitute the latest revision.

**Order timeline:** Render the actual timestamped transition history, not a falsely linear progress bar. Typical path: `Placed → Accepted → Shipped → Completed`; alternative handover: `Accepted → Completed`; branches: `Cancelled` and `Disputed`. A dispute is resolved by an administrator to Completed or Cancelled. Show actor, time and any permitted reason.

| Current state | Buyer controls | Seller controls | Administrator resolution |
| --- | --- | --- | --- |
| Placed | Cancel; Raise dispute | Accept; Cancel; Raise dispute | None unless a dispute is raised |
| Accepted | Confirm handover; Cancel; Raise dispute | Mark shipped; Cancel; Raise dispute | None unless a dispute is raised |
| Shipped | Confirm receipt; Raise dispute | Raise dispute | None unless a dispute is raised |
| Disputed | View case; supply permitted evidence | View case; supply permitted evidence | Resolve Completed or Cancelled with reason and evidence |
| Completed / Cancelled | View history; Report a concern where eligible | View history and permitted case links | No further order transition |

Confirmation dialogs repeat the action and current state. On a stale revision/order/case (`409`), preserve entered text, refresh server state and ask the user to review the changes. Never show a successful order/moderation result until committed. Retrying an uncertain order submission reuses its idempotency key; editing request facts requires a new request after reconciliation.

All order summaries state: `This is a purchase agreement. Payment and refunds take place outside this app.` Do not show Pay, Checkout, payment verified, escrow, refund issued or fabricated tracking integration.

**Mapping:** LIST-04–06; ORDER-01–07; REPORT-01; Architecture §§5, 7.2–7.3.

### G4. High-risk order warning modal

**Trigger:** An otherwise eligible buyer selects Place order for a currently High-risk listing. Risk alone never disables ordering. Use a shared order-review dialog for every listing, adding this warning section for High risk.

**Structure:** title `Review high-risk listing`; High-risk badge; exact revision, title and price; assessment timestamp; supplied factors; advisory `This listing has indicators associated with elevated risk. This is not a fraud verdict. Review the details before proceeding.`; agreement-only notice; `[Back to listing]` and `[I understand — place order]` buttons. Both remain keyboard reachable; no preselected consent.

Focus starts at the dialog heading or safe navigation action; trap focus while open, support Escape and restore focus to the trigger. A warning is not evidence that fraud occurred. For Medium show caution in order review; for Pending/Failed/Unassessed explain that there is no current assessment without forcing the High-risk wording.

Revalidate availability, account status and expected revision on submission. If revision or risk status changes during review, refresh the review before proceeding; do not place an order on unreviewed terms. After success show the order ID and actual Placed state. On uncertain network outcome, reconcile using the original request key before enabling another attempt.

**Mapping:** ORDER-01–04; LIST-08; PRD §§1, 4.4; Architecture §5.

### G5. Form feedback and file upload

- Show required/optional labels, help text, visible limits and field errors linked to the relevant input. On failed submission focus an error summary with links to invalid fields; retain valid non-secret text and explain when files need reselecting.
- Validate on the server; browser checks provide earlier feedback. Use specific copy: `Enter a price greater than 0`, `Choose a reason`, `Maximum 6 listing images`, `Maximum 3 evidence images`, `File exceeds 5 MB`, `Unsupported image format`.
- Listing images: zero to six; report evidence: zero to three. The request says evidence files, but PRD NFR-03 restricts P0 to JPEG, PNG or WebP images, up to 5 MB each. Reject SVG/executable files; validate decoded type and dimensions. Show filename, size, outline thumbnail placeholder, upload/validation status, remove action and count `2 of 6` / `1 of 3`.
- Do not expose a public URL for report evidence. Reject an extra/invalid file individually with a clear reason; keep accepted files and entered text when possible. A partial upload is not a successful publish/report.
- During submit show an inline progress label, disable repeated submit and preserve page context. Server limits and idempotency remain necessary. For session expiry preserve safe recoverable text, ask for sign-in and never automatically replay a mutation after login.
- Throttled actions show a safe retry message and server-provided retry timing. Network failures offer retry without duplicate submissions. Error panels may show a request ID, never a traceback or storage path.

**Mapping:** NFR-02–04, NFR-08–09; AUTH-01–02; LIST-01–02; REPORT-01.

### G6. Loading, empty, error and administrative audit components

**Loading:** outlined skeleton rows/cards labelled `Loading…`; busy regions announce once. Preserve already loaded content during polling. No fake count or fabricated result.

| Empty state | Copy and next action |
| --- | --- |
| Public catalog has no listings | `No listings available yet.` Offer Clear filters only if a filter is active. |
| Search/filter has no matches | `No listings match these filters.` `[Clear filters]`; preserve search and filter context. |
| Seller has no listings | `You have no listings yet.` `[Create listing]` only for an active seller. |
| Buyer has no orders | `You have not placed any orders.` `Browse listings`. |
| Seller has no sales | `No purchase agreements yet.` `View your listings`. |
| Buyer has no reports | `You have not submitted any reports.` Explain reporting starts from a listing/order. |
| Empty conversation | `No messages yet.` Short, neutral instruction to start the conversation if sending is permitted. |
| Admin queue has no cases | `No cases match the current filters.` Indicate filters or last refreshed time. |

**Error:** inline error panel with safe message, Retry where meaningful, preserved filters and last successful refresh time. Show `Data may be out of date` when polling fails; never reinterpret an error as an empty list or scan failure. Generic 403/404 gates avoid leaking private object details.

**AuditedAdminAction:** action name, target revision/account/configuration, reason, expected current state, confirmation, committed result with actor/time and `View audit event #ID` link to `/admin-app/audit-log/<audit_id>/`. Use it for verdicts/corrections, report transitions/assignment changes where privileged, listing removal/restoration, block/unblock, dispute resolution, explicit rescans, model activation/rollback, ruleset publication and exports. A failed audit write means the mutation failed; show no success. Expose no audit editing/deleting controls.

## Buyer App pages

### B1. Buyer landing and public listing browse

**Page name & route:** Browse listings — `/buyer-app/listings/`; `/buyer-app/` opens or redirects to this catalog.

**Layout structure**

1. Header: Buyer App name, navigation, Sign in / Register for visitors or account menu for members; G2 banner when applicable.
2. Search strip: page heading; full-text search input; `[Search]`; result count and sort control.
3. Desktop left rail (3 columns): category; minimum/maximum price; condition; location; risk filter `All / Low / Medium / High / Unassessed`; `[Apply filters]`; `[Clear filters]`.
4. Main grid (9 columns): reusable listing cards, three per row. Card order: thumbnail placeholder; title link; price/currency; seller display name; `Account age: N days/months` badge; G1 risk badge; availability label if needed.
5. Footer of results: page number, Previous, numbered pages, Next and result range. Preserve query/filters/sort in navigation.
6. Mobile: search first; `[Filters]` opens a labelled panel; single-column cards; pagination below results.

**UI components:** BuyerShell, SearchForm, FilterPanel, SortSelect, ListingCard, AccountAgeBadge, RiskBadge, Pagination, EmptyState, InlineError.

**Special UI states:** Initial skeletons; empty catalog versus no matches; invalid price range (minimum greater than maximum); failed result load with retry; unavailable category; pending/scanning/failed/stale cards per G1; expired session affects protected actions while public browsing remains accessible. Risk status refresh preserves grid position. Pagination clamps or explains a now-empty page.

**Important UX notes / PRD mapping:** LIST-01–03, LIST-07–08, AUTH-05, AC-04. Query only visible public listings; show current revision summaries. Default All includes High-risk and unassessed listings. An explicit Low filter excludes stale/pending/failed records. Stable secondary sorting avoids duplicate/skipped cards between pages. Do not expose seller email or imply that an older account is verified trustworthy.

### B2. Listing detail

**Page name & route:** Listing detail — `/buyer-app/listings/<product_id>/`. Historical snapshot — `/buyer-app/listings/<product_id>/revisions/<revision_no>/`, subject to visibility and authorized-history access.

**Layout structure**

1. Header and breadcrumb `Browse > Category > Listing`.
2. Main row: left 7 columns gallery with large crossed placeholder, thumbnail placeholders and image count; right 5 columns title, condition, location, price/currency, availability, seller name and account age.
3. Prominent assessment panel beside/below price: G1 badge; current listing revision; exact assessed revision; assessment and feature timestamps; factors; advisory copy. For non-ready states show `Current revision rN — no current completed assessment` and any queued/scanning status.
4. Action group: `[Contact seller]`, `[Place order]`, `Report this listing`. Include agreement-only notice and explanation for unavailable actions.
5. Description, product facts and expandable `Revision history` panel. History rows show rN, created time, change summary and permitted snapshot link; expansion does not replace the current assessment with an old one.
6. Mobile: gallery, facts, risk panel, actions, description/history. Any sticky action area must leave warning text and keyboard-focused content visible.

**UI components:** GalleryPlaceholder, SellerSummary, RiskAssessmentPanel, ObservedFactors, RevisionReference, AvailabilityLabel, ActionGroup, RevisionAccordion, OrderReviewModal/G4.

**Special UI states:** No photos shows `No photos supplied — limited listing evidence`; zero returned factors; pending/scanning, failed and unassessed/stale; older assessed revision shown only as historical; removed/unavailable listing; reserved/sold listing disables ordering due to availability; blocked buyer; inactive seller; own listing disables self-contact/order/report. Visitors sign in before a protected action and return to this revision for review. A changed revision or competing purchase produces a reviewable conflict, not a new order on different facts.

**Important UX notes / PRD mapping:** LIST-01–08; ORDER-01–03; REPORT-01; SCAN-06–07. High risk remains orderable when all business eligibility checks pass, with G4. Viewing an authorized historical order snapshot does not permit a new order against an obsolete revision. Historical snapshots and images of hidden listings require appropriate access; the public history panel must not reveal private evidence or bypass removal.

### B3. Buyer registration and login

**Page name & route:** Buyer authentication — `/buyer-app/register/` and `/buyer-app/login/`.

**Layout structure**

1. Minimal Buyer header and `Back to browse` link.
2. Centered narrow form card with clearly linked Register / Sign in views.
3. Registration: full name, email, password, password confirmation, password requirements, `[Create buyer account]` and existing-account sign-in link.
4. Login: email, password, `[Sign in]`; show password visibility control with an accessible label.
5. Form-level feedback; secondary link to Seller App sign-in. Existing authenticated users without buyer membership see an explicit `Enable buyer access` account action if eligible.

**UI components:** AuthShell, LabelledInput, PasswordInput, PasswordHelp, ErrorSummary, SubmitButton, RoleAccessPrompt.

**Special UI states:** Required/invalid fields; password mismatch/validator errors; duplicate case-insensitive email routes the user to the existing-account flow without creating a second identity; login failure uses generic `Email or password is incorrect`; throttling; session expiry; submit in progress; authenticated member; blocked member can sign in for permitted history but cannot add roles. No empty-data state; show a normal blank form.

**Important UX notes / PRD mapping:** AUTH-01–06; NFR-04. Registration grants buyer membership only. Existing-account guidance must follow the server's privacy policy without leaking account status through login errors. Validate return URLs; signing in must not automatically submit a pending order/report. Use actual Django password rules; never show stored passwords or a public administrator option.

### B4. My orders — buyer

**Page name & route:** My orders — `/buyer-app/orders/`; order detail — `/buyer-app/orders/<order_id>/`.

**Layout structure**

1. Buyer header; page title; agreement-only notice.
2. Status filter `All / Placed / Accepted / Shipped / Completed / Disputed / Cancelled` and optional order ID search.
3. List/table: order ID/date, product snapshot title/placeholder, seller, ordered revision, agreed price/currency, current state and `[View order]`; pagination.
4. Selected order detail: immutable ordered snapshot and current-listing link separately; actual G3 event timeline; eligible actions; conversation link; `[Report a concern]` with this order context.
5. Placed detail: `Awaiting seller response` and server-provided expiry timestamp, initially 48 hours after placement. Accepted detail offers `[Confirm handover]`; Shipped offers `[Confirm receipt]`.

**UI components:** OrderList, OrderStatusFilter, OrderSnapshot, OrderTimeline, TransitionButtons, ActionConfirmation, DisputePanel, Pagination.

**Special UI states:** Loading; no orders/no filtered results; forbidden order; removed listing but authorized order snapshot retained; concurrent transition/expiry; failed action with unchanged state; repeated request returns existing result; disputed case awaiting admin; blocked account retains permitted existing-order actions. Display Pending/Failed/historical risk through G1 if a risk panel is included; it never changes agreed terms.

**Important UX notes / PRD mapping:** ORDER-01–07; LIST-05; REPORT-01. G3 defines controls precisely; no Cancel after Shipped, no buyer/seller dispute resolution and no transition from terminal states. Accepted can complete through confirmed in-person handover without Shipped. Do not show payment/refund claims or imply that cancellation restores an admin-removed listing.

### B5. Private chat — buyer

**Page name & route:** Messages — `/buyer-app/conversations/`; conversation — `/buyer-app/conversations/<conversation_id>/`.

**Layout structure**

1. Buyer header; desktop left conversation list with seller, listing title and last-message time.
2. Main header: seller and linked product summary, listing availability and `Last refreshed [time]`.
3. Message history: chronological text bubbles/outlined rows, sender label and sent time; `[Load older messages]` above. Buyer-sent messages show `Not read` or `Read at [timestamp + timezone]` from the recipient's stored receipt.
4. Polling status line: `Checking for new messages` / `Updates paused` / `Reconnecting` and a manual refresh control.
5. Composer: visible label, multiline message, `N/4000` character counter and `[Send]`; restriction or rate-limit message nearby. Mobile uses a conversation list page then a full-width thread with Back link.

**UI components:** ConversationList, ProductContextStrip, MessageList, MessageBubble, ReadReceipt, PollStatus, MessageComposer, LoadOlderButton.

**Special UI states:** Empty inbox/thread; loading older messages; request failure retains history and draft; send pending/failed with explicit retry after reconciliation; blocked sender makes composer unavailable but history readable; role/participant denial; session expiry; duplicate or out-of-order polling responses do not duplicate messages. New messages show a `New messages` jump control if the user is reading above the bottom.

**Important UX notes / PRD mapping:** CHAT-01–04; AUTH-03; NFR-02. Poll approximately every five seconds using bounded `after_id` pages; back off after errors and avoid overlapping requests. Only mark incoming messages read when the recipient actually views them; do not infer a read receipt from a successful poll alone. One conversation per listing/buyer, no self-conversations. No WebSocket, fabricated online/typing status or AI inspection of private chats.

### B6. Submit fraud report

**Page name & route:** Report listing — GET `/buyer-app/listings/<product_id>/reports/new/`; submit with POST `/buyer-app/listings/<product_id>/reports/`. An optional validated order reference fixes the purchased revision.

**Layout structure**

1. Buyer header; Back to listing/order; heading `Report a concern`.
2. Read-only target card: product ID/title, exact Reported revision, seller and linked snapshot. If order-linked, show order ID and purchased revision prominently.
3. Reason dropdown: Misleading description, Suspicious price, Duplicate listing, Non-delivery, Counterfeit, Other (schema values mapped to readable labels).
4. Required comment field with `N/5000` counter; help `Describe what you observed; avoid sharing unnecessary personal information`.
5. Private evidence upload per G5, `0 of 3 images`; privacy note `Visible only to you and authorized administrators`.
6. `[Cancel]` and `[Submit report]`; success panel with report ID, Pending state and `View my report` link.

**UI components:** ReportTargetSnapshot, ReasonSelect, CommentField, EvidenceUploader, PrivacyNote, ErrorSummary, SubmitState, SuccessReceipt.

**Special UI states:** Missing reason/comment; rejected type/size/fourth attachment; no attachments (allowed); upload failure; stale current revision; own listing rejected; invalid/non-owned order reference; session expiry; throttling; submission pending/failed. For changed current revision, preserve the comment and re-review the target before submission; never silently switch rN. For existing-order evidence after blocking, retain the permitted workflow.

**Important UX notes / PRD mapping:** REPORT-01–03; LIST-04–05; NFR-01–03. A new non-order report targets the current revision; an order-linked report targets the immutable purchased revision. The backend derives reporter identity and verifies order ownership. Filing a report is an allegation, not a fraud verdict. No automatic seller access to attachments; no false promise of a response time.

### B7. My submitted reports

**Page name & route:** My reports — `/buyer-app/reports/`; report detail — `/buyer-app/reports/<report_id>/`.

**Layout structure**

1. Buyer header; title; state filter `All / Pending / Reviewing / Resolved / Dismissed`.
2. Report rows: report ID/date, listing title, exact reported revision, reason, status, last update and `[View report]`; pagination.
3. Detail: original report text, private evidence placeholders/download links, target revision and optional order reference.
4. Status history with timestamps and public-facing outcome. Separate `Report status` from any disclosed moderation verdict or AI assessment; return link to the associated order.

**UI components:** ReportList, ReportStatusBadge, RevisionReference, PrivateAttachmentList, CaseStatusTimeline, OutcomePanel, Pagination.

**Special UI states:** No reports/no matching status; loading/error; removed listing with authorized snapshot; unavailable evidence file with retry/support reference; awaiting review/outcome; blocked account retains history/evidence access; unauthorized report returns generic unavailable. If risk is shown, use G1 and label the correct revision/time.

**Important UX notes / PRD mapping:** REPORT-02–05; AUTH-03; NFR-01. Show only the user's reports and public-facing outcomes; never expose internal notes, other reporters or attachments. Dismissed does not imply legitimate. Resolved does not itself identify a verdict. Do not add P1 appeals/notifications to the P0 page as functional controls.

## Seller App pages

**Supporting authentication routes:** `/seller-app/register/` and `/seller-app/login/` reuse B3's form structure with seller-specific labels and grant/check seller membership. Existing accounts sign in and explicitly enable seller access rather than registering duplicate identities. These supporting auth views do not add a new page family to the five requested Seller pages.

### S1. Seller dashboard

**Page name & route:** Seller dashboard — `/seller-app/`; Listings view/filter — `/seller-app/listings/`.

**Layout structure**

1. Seller header and G2 banner; heading; `[Create listing]`.
2. Three metric boxes with definitions: Active listings (visible Available/Reserved), Sold listings (Sold availability), High-risk active listings (current `ready` High among active listings). Each count links to its list filter.
3. Filter strip: availability, visibility, assessment state/risk and title search.
4. Own-listings table: thumbnail placeholder; title/current revision; price; availability; visibility; scan job status; G1 risk badge; last assessment time; `[View]`, `[Edit]`, `[Revision history]`. Eligible available listings also expose a confirmable Withdraw action.
5. Scan status legend and pagination. Mobile converts rows into labelled stacked cards.

**UI components:** SellerShell, MetricCard, ListingFilter, SellerListingRow, ScanJobStatus, RiskBadge, RevisionLink, WithdrawalConfirmation, Pagination.

**Special UI states:** No listings; no matching filter; pending/unbound job, scanning, retry scheduled, failed, superseded historical job; stale assessment; metrics/list fetch failure; reserved/sold edit lock; administrator removal; blocked seller disables creation/edit/publication while retaining sales/history access. Do not replace unavailable metric data with zero.

**Important UX notes / PRD mapping:** LIST-03–06; SCAN-02–09; APP-03. Scan-job status and risk result are separate columns: Succeeded does not ensure a result is still current. High-risk count excludes old results and never triggers automatic withdrawal. Withdrawing an available listing is soft removal; active orders require permitted cancellation/dispute handling first. Metric definitions above are proposed UI counting conventions to keep consistent in server queries.

### S2. Create / edit listing

**Page name & route:** Create — `/seller-app/listings/new/`; edit — `/seller-app/listings/<product_id>/edit/`. Draft creation uses POST `/seller-app/listings/`; publication uses POST `/seller-app/listings/<product_id>/publish/`.

**Layout structure**

1. Seller header; Back to listings; heading `Create listing` or `Edit listing #ID`; current revision/availability and any lock reason.
2. Main form (8 columns): title; description; category; price with configured currency; original price labelled Optional; condition `Like new / Good / Fair / Poor`; location.
3. Image panel: drag/drop or browse control; count `N of 6`; image placeholders in order with Remove/Reorder; `Photos are optional` help.
4. Side summary (4 columns): draft/publication state; revision rules; validation summary; preview of title/price/placeholder. On mobile place it after fields.
5. Footer actions: `[Save draft]`, `[Publish listing]` for a draft; `[Save draft changes]` and `[Publish new revision]` for permitted edits to an available listing; Cancel link. Explain that saving edit-draft changes does not replace the public revision.
6. Committed publication receipt: `Published as revision rN. Scan queued.`; link to listing and revision history; G1 pending state. Risk checks must not block publication while the worker is unavailable.

**UI components:** ListingForm, CategorySelect, ConditionSelect, CurrencyInput, ImageUploader, DraftStatus, RevisionNotice, PublishConfirmation, ScanQueuedReceipt.

**Special UI states:** New blank form; loading draft/edit; partial draft versus publication validation; invalid price/category/length; seventh image/type/size failure; missing image allowed; save/upload/publish pending or failed; unsaved changes; stale edit conflict; active-order/completed-sale edit lock; blocked seller; removed-by-admin listing has no implicit restore action. Successful draft save produces no scan; publication failure never displays Scan queued.

**Important UX notes / PRD mapping:** LIST-01–06; SCAN-01–02; NFR-02–03. Title max 200, description max 20,000 and location max 150 characters match reference schema; price must be positive, optional original price nonnegative. Do not invent a rule that original price must exceed selling price. Every published material change creates an immutable revision and retains earlier images. Incomplete draft storage must be defined separately because `product_revisions` requires complete validated content; do not write invalid partial revisions. Existing-listing edit drafts are a proposed UI contract needing a private draft representation, never edits to the public revision.

### S3. Seller listing revision history

**Page name & route:** Listing history — `/seller-app/listings/<product_id>/revisions/`; revision detail — `/seller-app/listings/<product_id>/revisions/<revision_no>/`; assessment history GET `/seller-app/listings/<product_id>/risk-history/`.

**Layout structure**

1. Seller header; listing identity; current availability/visibility; `[Back to listing]`.
2. Current-revision summary, current G1 risk state and edit eligibility.
3. Revision table newest first: rN, created/published time, changed fields, recorded price/currency, image count, `Current` or `Historical`, `[View snapshot]`.
4. Expanded snapshot: saved fields and image placeholders; assessment history table with job/result ID, job state, context, model/ruleset, feature timestamp, assessment time and historical risk result. Clearly identify the one currently applicable result, if any.
5. Optional `Compare selected revisions` disclosure may show plain text field differences; no revert-in-place control.

**UI components:** RevisionTable, RevisionSnapshot, ChangeSummary, AssessmentHistoryTable, ScanJobStatus, HistoricalRiskBadge, ModelRuleReference.

**Special UI states:** Single revision; draft with no published revision; no assessment history; queued/scanning, terminal failed or superseded jobs; old successful result after a newer revision; stale results; missing historical media; unauthorized listing; load failure. No current score is inferred from a historical row.

**Important UX notes / PRD mapping:** LIST-04–05; ORDER-02; REPORT-01; SCAN-03–08. Read only for historical content. Several assessments may belong to one revision when context/model/rules change. Orders/reports retain their original revision; show only seller-authorized references and no reporter-private evidence. Any future restore-copy operation would create a new revision, not mutate rN.

### S4. Sales / my orders — seller

**Page name & route:** Sales — `/seller-app/orders/`; sale detail — `/seller-app/orders/<order_id>/`; actions POST `/seller-app/orders/<order_id>/actions/`.

**Layout structure**

1. Seller header; Sales heading; agreement-only notice.
2. State filter and paginated rows: order ID, buyer display name, ordered title/revision, agreed price/currency, placed time and current state.
3. Selected sale: immutable snapshot; G3 timeline; linked buyer conversation; action group `[Accept]`, `[Cancel]`, `[Mark shipped]`, `[Raise dispute]` only when allowed.
4. Placed sale shows seller-response expiry; each mutation opens a focused action/confirmation form. Disputed sale shows case link and permitted evidence entry; terminal sale shows history.

**UI components:** SalesTable, OrderSnapshot, OrderTimeline, TransitionButtons, ActionConfirmation, DisputePanel, Poll/RefreshStatus, Pagination.

**Special UI states:** No sales/no filtered matches; loading/error; auto-expired Placed order; competing buyer cancellation; concurrent action conflict; repeated submit; disputed awaiting admin; removed listing still retains order snapshot; blocked seller retains authorized existing fulfilment/cancellation/dispute actions. Listing scan pending/failed never prevents an allowed fulfilment action.

**Important UX notes / PRD mapping:** ORDER-02–07; APP-03. Accept only from Placed; Ship only from Accepted; Cancel only from Placed/Accepted; dispute from Placed/Accepted/Shipped. Seller cannot mark Completed or resolve a dispute. Buyer confirms receipt/handover. Cancellation does not automatically restore visibility. Never imply shipping or payment has been externally verified.

### S5. Private chat — seller

**Page name & route:** Messages — `/seller-app/conversations/`; thread — `/seller-app/conversations/<conversation_id>/`.

**Layout structure**

1. Seller header; left list of existing conversations labelled by buyer and listing.
2. Thread header: buyer display name, listing summary, optional authorized sale link and last refresh time.
3. Chronological messages and `[Load older messages]`; seller-sent messages show recipient `Read at [timestamp + timezone]` or Not read.
4. Poll status line and labelled composer with `N/4000`, `[Send]` and contextual feedback. Mobile uses separate inbox and thread views.

**UI components:** Reuse B5 ConversationList, ProductContextStrip, MessageList, ReadReceipt, PollStatus, MessageComposer; vary role labels and related order links.

**Special UI states:** No conversations/empty thread; polling interrupted or throttled; unsent draft; send failure; session expiry; blocked seller read-only; nonparticipant denial; unavailable listing; duplicate/out-of-order message pages. Pending/failed scan belongs to an optional product risk summary, never to message delivery status.

**Important UX notes / PRD mapping:** CHAT-01–04; AUTH-03; APP-03. Use the same conversation records and polling rules as B5; no seller-only copy of message history. Show only buyers who already have a valid conversation about that seller's product; no unsolicited new-conversation broadcast tool. Only the receiving participant marks incoming messages read.

## Admin App pages

All Admin pages require a separately provisioned, authorized administrator. Reuse a restricted sign-in form at `/admin-app/login/` with no Register link; preserve a safe return path. Membership, status and object/evidence authorization apply to every request, including downloads and polling. Administrator identities do not buy or sell in P0.

### A1. Admin dashboard overview

**Page name & route:** Admin overview — `/admin-app/`.

**Layout structure**

1. Admin header/navigation; administrator identity; last refreshed timestamp and `[Refresh]`.
2. Metric boxes: Total listings; Medium-risk listings; High-risk listings; Open fraud reports; Failed scan jobs. Define totals and scope beneath the labels: all listing records including hidden/draft for Total; current `ready` results for risk counts; Pending/Reviewing reports for Open; selected-period terminal job failures for Failed.
3. Left wide panel: review queue preview with source, listing/revision, current risk, open report count and oldest waiting time.
4. Right panel: scan operations summary with queued/running/terminal-failed counts, oldest queued age and active model/ruleset. Failed count expands an in-page job table with listing/revision, job ID, sanitized error, attempt count and next retry if scheduled. An eligible `[Request rescan]` requires a reason and G6 audit receipt; it creates new assessment context without rewriting failed history. Configuration links lead to A3.
5. Order-dispute summary with count and link into the review workspace's dispute view, separate from AI/report cases. No fake charts are required.

**UI components:** AdminShell, MetricCard, QueuePreview, ScanOperationsSummary, FailedJobTable, AuditedRescanAction, ConfigurationSummary, DisputeSummary, RefreshStatus.

**Special UI states:** Loading; genuinely zero counts; unavailable metric shown as Unknown rather than zero; no cases; no active model/ruleset; worker delayed; failed/scanning/stale summaries; session expired/forbidden. A worker outage degrades assessment, not the catalog's availability.

**Important UX notes / PRD mapping:** ADMIN-01–03; SCAN-07–09; APP-01–03; NFR-08. Predictions and confirmed decisions remain separate counts. Failed-job counts are not fraud counts and risk totals omit unassessed records. Use clear count scope/filter links to avoid comparing incompatible populations. Any mutation accessed from here uses G6 and links to its audit event.

### A2. Moderation review queue and case workspace

**Page name & route:** Queue — `/admin-app/reviews/`; case — `/admin-app/reviews/<product_id>/?revision=<revision_no>`. Dispute subview — `/admin-app/reviews/?type=order-dispute`, detail `/admin-app/reviews/orders/<order_id>/`.

**Layout structure**

1. Admin header; filters for source `All / AI alert / User report`, risk, case/report status, assignment and age; order-dispute toggle kept distinct.
2. Queue list/table (4 columns): one row per listing, source chips, exact involved revisions, current risk, open report count, assigned reviewer and oldest waiting time. Rank current High risk, then oldest waiting cases; paginate.
3. Case pane (8 columns), section 1: product/revision selector, immutable snapshot, seller display identity/status/account age, current availability/visibility. Clearly label reported historical revisions separately from the current one. For each open report show its assigned reviewer, `[Assign to me]`, and an authorized reviewer selector with `[Reassign report]`; use G6 audit/conflict handling. An AI-only listing alert has no report assignment unless an explicit case-assignment mechanism is implemented.
4. Section 2: assessment evidence for the selected revision—score `n/100` when applicable, current/historical indicator, assessed/feature timestamps, model/ruleset and observed factors. Distinct section for canonical human verdict and decision chain.
5. Section 3: each report's reason/text, exact revision, assignment/status and private evidence placeholders with authorized Open/Download. AI-only cases show `No user report attached`.
6. Decision form: verdict radio group `Fraud / Legitimate / Unresolved`; required review reason and evidence summary; `[Record verdict]`, or `[Append correction]` with the prior decision reference when correcting. Separate controls for `[Remove listing]` / `[Restore listing]`, `[Block user]` / `[Unblock user]`, and a report status selector with `[Update report status]`. Each action shows its precise target and uses G6 confirmation/audit receipt.
7. Dispute subview: order snapshot, actual transition history, evidence and resolution selector `Completed / Cancelled`; required reason/evidence; `[Resolve dispute]` and resulting audit link.

**UI components:** ModerationQueue, SourceChip, RevisionSelector, RevisionSnapshot, SellerAccountPanel, AssessmentEvidence, PrivateAttachmentViewer, ReportStatusForm, DecisionChain, ModerationActionForm, DisputeResolutionForm, AuditReceipt.

**Special UI states:** Empty/no matching queue; AI-only/report-only/combined case; selected old revision while current scan is pending/failed/stale; evidence missing or denied; case claimed/changed by another admin; stale chain head; previous verdict correction; already removed/blocked target; upload/action failure; audit failure rolls back action; forbidden/session expired. On conflict reload the chain/status and preserve unsubmitted reasoning for review.

**Important UX notes / PRD mapping:** REPORT-01–05; ADMIN-01–03; ORDER-04, ORDER-07; AC-14–15. Deduplicate at listing level without merging revisions or evidence into one generic case. AI alerts are not user reports or verdicts. No preselected fraud verdict and no automatic block/remove from High risk. Verdict, report resolution and moderation actions are distinct explicit decisions; a verdict alone does not resolve a report. Corrections append to the immediate predecessor, never overwrite history. New Unresolved decisions remove the prior label from later eligible exports. Blocking preserves existing-order obligations; removed listings preserve authorized snapshots/evidence.

### A3. Risk-model and ruleset management

**Page name & route:** Models and rules — `/admin-app/models/`; model detail — `/admin-app/models/<model_id>/`; rulesets — `/admin-app/rulesets/`; ruleset detail — `/admin-app/rulesets/<ruleset_id>/`.

**Layout structure**

1. Admin header; active configuration strip showing model version, ruleset version and activation time/audit link.
2. Models table: immutable version, algorithm, feature schema, dataset version, registered time, trusted artifact/checksum verification state, Registered/Active/Retired status and `[View evaluation]`. Eligible rows offer `[Activate]`; previous registered versions offer `[Roll back to this version]`.
3. Evaluation drawer/detail: dataset/split versions, sample counts and prevalence, fraud precision/recall/F1/average precision, confusion matrix with labels/counts, baseline comparison (rules and Logistic Regression) on matching splits, synthetic/real and category slices, limitations and false-positive examples. Absent evaluations read `Not evaluated`; missing measurements read `Not measured`; mathematically undefined metrics read `Not defined`, never zero by default.
4. Rulesets table: version, Draft/Active/Retired status, thresholds/feature-schema compatibility, publisher/time and `[View]`. Draft editor exposes validated thresholds and versioned rule content; `[Publish new version]` creates immutable published contents.
5. Activation/publication/rollback confirmation: current versus proposed configuration, compatibility status, required reason, affected available-listing scope, warning `Existing results may become outdated; reassessments will be queued`, confirm action.
6. Success receipt: new active pair, audit link and recoverable rescan-campaign progress summary. Preserve previous configuration history.

**UI components:** ConfigurationSummary, ModelVersionTable, EvaluationSummary, ConfusionMatrixTable, DatasetProvenance, RulesetVersionTable, ThresholdForm, ConfigurationChangeDialog, RescanCampaignStatus, AuditReceipt.

**Special UI states:** No registered model/ruleset/evaluation; no active compatible pair leaves listings awaiting assessment; incompatible schema/class mapping/dependencies; invalid thresholds; incomplete/unverified artifact; stale configuration/concurrent activation; failed activation/audit; queued/running/failed rescan campaign. Configuration failure preserves the previous active pair. Scan completion is asynchronous and must not be claimed immediately.

**Important UX notes / PRD mapping:** PRD §§4.3–4.4, 7.3; SCAN-02, SCAN-06–09; ADMIN-02; AC-16, AC-18–19. Initial thresholds are Low 0–39, Medium 40–74, High 75–100; actual display follows the bound version. Validate `0 <= medium_min < high_min <= 100`. Activation/rollback validates a compatible model/ruleset pair atomically even when initiated from one row. Published contents and registered artifacts are immutable; changes require a new version. No unrestricted artifact upload, inline retraining, automatic promotion, fabricated metrics or real-world accuracy claim based on synthetic-only evaluation.

### A4. Admin audit-log browser

**Page name & route:** Audit log — `/admin-app/audit-log/`; event detail — `/admin-app/audit-log/<audit_id>/`.

**Layout structure**

1. Admin header; `Audit log — read only` heading.
2. Filter form: actor/user, action type, from/to date-time with timezone; optional target ID and event ID; `[Apply]`, `[Clear]`.
3. Paginated table ordered by timestamp plus event ID: event ID, timestamp, actor, action, target type/ID/revision, reason excerpt and `[View event]`.
4. Detail drawer/page: complete safe reason, target links, permitted before/after values, related case/order/configuration/export IDs and request/correlation ID. Back link preserves filters.

**UI components:** AuditFilterForm, DateRangeInput, AuditTable, AuditEventDetail, TypedTargetLink, Pagination, EmptyState.

**Special UI states:** Empty audit log/no matching filters; invalid range; loading/network failure; historical target no longer public but authorized immutable reference retained; missing/forbidden detail; session expiry. Missing optional values display `Not recorded`, not invented text. Assessment state is a recorded payload fact where relevant, not a live badge overwritten with today's result.

**Important UX notes / PRD mapping:** ADMIN-02; NFR-06, NFR-08; AC-15. Every privileged-action success elsewhere links here. Audit entries are append-only and access-controlled; expose no edit/delete controls or passwords/session tokens/raw private messages. This page's date-range filter is not a bulk-delete mechanism.

### A5. Export dataset

**Page name & route:** Export dataset — GET `/admin-app/exports/`; version detail — `/admin-app/exports/<dataset_id>/`; creation POST `/admin-app/exports/`.

**Layout structure**

1. Admin header; heading and `Administrator-only training/research export` description.
2. Export configuration card: dataset version/name, source selection (Project synthetic / Eligible reviewed records, kept identifiable), immutable cutoff time, feature-schema version and permitted scope/category/date filters; required export reason.
3. Eligibility preview: included record count and separate exclusion counts for unresolved/no eligible decision, insufficient evidence, missing point-in-time features or schema mismatch. Show source/synthetic breakdown and schema/provenance column summary without personal data.
4. Rules panel: latest effective canonical decision at cutoff first; eligible evidence-backed Fraud/Legitimate only for reviewed labels; no AI-derived labels. Newer Unresolved excludes an older label. Synthetic labels are explicitly generator-provided.
5. `[Generate versioned export]` with confirmation of scope/cutoff/reason; progress or committed receipt. Completed detail: dataset version, cutoff, row/source counts, checksum, feature schema, label policy and provenance; `[Download data]`, `[Download manifest/data dictionary]`, split-manifest reference where one exists; `View audit event`.
6. Previous exports table: version, created/cutoff times, creator, source mix, state, record count, checksum/detail and audit links. Mobile stacks configuration before history.

**UI components:** ExportConfigurationForm, EligibilitySummary, PrivacyAndLabelPolicy, DatasetVersionTable, ExportStatus, ManifestSummary, AuthorizedDownload, AuditReceipt.

**Special UI states:** No eligible records/no prior exports; invalid cutoff/range; duplicate immutable version name; unavailable/mismatched feature schema; preview stale before generation; generation/storage failure; network-uncertain result reconciled before another export; unauthorized/expired download. If generation runs asynchronously, show Queued/Generating/Ready/Failed as export states, distinct from scan states; the durable export-job mechanism is an implementation decision, not an assumed existing table/API.

**Important UX notes / PRD mapping:** DATA-01–08; REPORT-05; AUTH-05; ADMIN-02; NFR-05–06; Architecture §9. Exclude names/emails/contact details, credentials, raw private chats and report attachments. Use pseudonymous stable grouping keys, revision identity, feature timestamps, schema, label source/decision time, source/generator metadata and synthetic flags for reproducibility. Keep identifiers/provenance separate from predictor columns. Export only point-in-time-eligible features; if historical snapshots are unavailable, exclude rather than reconstruct from current data. Partition/group handling and split manifests belong to the dataset/training pipeline; do not imply export alone prevents leakage. Successful export and required audit commit together; failure creates no successful downloadable version.

## Frontend implementation notes

- **Reuse:** Django templates and Bootstrap with small local JavaScript modules. Shared partials: app shell/navigation, RiskBadge/AssessmentPanel, RevisionReference, AccountRestrictionBanner, ListingCard, OrderSnapshot/Timeline, ConversationThread, Uploader, ErrorSummary, Pagination, EmptyState and AuditedAdminAction. Parameterize role labels/permissions rather than duplicating business logic.
- **Server authority:** render capabilities from shared services after membership/status/ownership checks. Hide or explain irrelevant controls, but enforce the same rules in CSRF-protected POST handlers. Use POST/redirect/GET; GET never mutates. Map invalid input, forbidden access, private not-found, stale-state conflict and throttling to distinct safe feedback.
- **Polling:** share bounded message/risk refresh utilities; no overlapping requests, preserve drafts/scroll/focus, deduplicate by stable IDs, back off after failures and resume with reconciliation. Polling errors mean `Unable to refresh`, never `Scan failed`. State refresh cannot replace an ordered/reported revision with current content.
- **Accessibility:** semantic headings/landmarks/tables, labelled inputs, error associations and summaries, visible keyboard focus, logical tab order, focus restoration for dialogs, and nonintrusive live regions. Icons accompany text; offer reduced motion and sufficient contrast. Tables need mobile labelled equivalents; keyboard access and zoom must work without horizontal page clipping.
- **Risk display:** use one server-derived currentness/state contract across apps. Keep labels/symbols in monochrome. Production colors are supplementary. Show exact assessment revision/time; stale/failed/pending/unassessed never receive a current numeric default. Historical results always say Historical and retain their own timestamps/model/ruleset. Observed factors are contextual signals, not causal proof.
- **Forbidden behavior:** no automatic hiding/blocking solely from AI risk; no safe/verified-seller promise from Low risk/account age; no unassessed-as-Low mapping; no mutation of published revisions; no current-content substitution in orders/reports; no public private-evidence URLs; no report dismissal-as-legitimate label; no payment gateway/escrow/refund-verification UI; no P0 WebSockets or private-chat model inspection; no privileged mutation without its audit link; no block overlay that prevents permitted existing-order obligations.
- **Implementation decisions to finalize:** private partial/edit-draft storage; deactivated-account access; export execution/download formats and durable progress if asynchronous; configured field/upload/rate limits and dataset/model registration process. The reference SQL is authoritative for existing constraints, while these proposed page routes and interactions still need application implementation.

**Wireframe handoff check:** Review all 17 pages in normal, loading, error, empty and restricted states; exercise every badge state, High-risk order review, changed-revision conflict, both order-completion paths, disputed resolution, worker outage/recovery, private evidence access and audit failure. This is a design QA checklist, not a statement that runtime tests have passed.
