# Buyer App and shared marketplace workflows

`/listings/` uses PostgreSQL full-text search over each public product's current revision, active seller status, category, price, condition, location and current-risk filters. Search is parameterized, bounded and paginated with a product-ID tiebreaker. The Low filter requires a current completed Low result; missing/failed/stale scores are never substituted with zero.

Purchases POST a random request UUID plus the exact displayed revision. The shared service fingerprints those immutable facts and invokes `place_order`; the database serializes replay identities and competing purchases. High-risk purchases require an explicit server-checked acknowledgement. Orders retain purchased terms and use `transition_order` with the expected state and a reason. Blocked/deactivated participants keep existing fulfilment, cancellation and dispute obligations; only administrators resolve a disputed order. No page claims a payment was processed.

Conversation creation derives the seller from the listing. Buyer and Seller routes share participant checks, bounded message polling and recipient-only initial read updates. Chat text is escaped or inserted using `textContent`, never interpreted as HTML. Polling preserves the composer and scroll position, pauses while hidden, prevents overlapping polls and backs off after failure. Private chats are excluded from model features and exports.

Active buyers submit concerns with an explicit target revision or an owned order's purchased revision. Pillow validates up to three private evidence images. Their contents are served only through an authorization-checked endpoint, with private/no-store caching. Reporters can append evidence to an existing open case after marketplace restriction; unrelated users and the reported seller cannot retrieve it. Reports remain allegations until independent evidence-backed administrator decisions.

Run the focused PostgreSQL checks with the setup environment:

```powershell
python -m pytest tests/integration/test_buyer.py tests/integration/test_evidence.py -q --reuse-db
```

The direct database regression suite separately exercises a two-connection competing-purchase race. See the delivery evidence for checks actually executed, workload measurements and remaining acceptance limits.

Current scan/publication, appeals and background process policy: [OPERATIONS.md](OPERATIONS.md). Public listing access requires a current successful scan; submitted does not mean publicly released.
