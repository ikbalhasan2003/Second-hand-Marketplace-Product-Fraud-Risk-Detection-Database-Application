-- Representative READ-ONLY queries. Apply 001..006 first.
-- End-user identifiers below are explanatory fixtures. Production code takes them
-- from the authenticated session, uses bound parameters, and checks authorization.

-- 1. Public current-listing search: expression matches the GIN index exactly.
-- 'simple' avoids assuming a stemming language before one is selected.
EXPLAIN (ANALYZE,BUFFERS)
SELECT p.product_id,v.title,v.price,v.currency,v.condition,v.location,
       r.assessment_state,r.risk_score,r.risk_level
FROM products p
JOIN product_revisions v ON (v.product_id,v.revision_no) = (p.product_id,p.current_revision_no)
JOIN users seller ON seller.user_id = p.seller_id
LEFT JOIN current_listing_risk r ON r.product_id = p.product_id
WHERE p.availability = 'available' AND p.visibility = 'visible'
  AND seller.status = 'active' AND seller.is_active
  AND to_tsvector('simple'::regconfig,v.title || ' ' || v.description)
      @@ websearch_to_tsquery('simple'::regconfig,'desk lamp')
ORDER BY p.created_at DESC,p.product_id DESC LIMIT 20;

-- 2. Low-risk filter: pending/failed/stale rows never qualify as low risk.
SELECT p.product_id,v.title,r.risk_score
FROM products p
JOIN product_revisions v ON (v.product_id,v.revision_no) = (p.product_id,p.current_revision_no)
JOIN users seller ON seller.user_id = p.seller_id
JOIN current_listing_risk r ON r.product_id = p.product_id
WHERE p.availability = 'available' AND p.visibility = 'visible'
  AND seller.status = 'active' AND seller.is_active
  AND r.assessment_state = 'ready' AND r.risk_level = 'low'
ORDER BY v.price,p.product_id LIMIT 20;

-- 3. Unassessed listings include pending, scanning, failed and stale states.
SELECT p.product_id,r.assessment_state
FROM products p JOIN current_listing_risk r USING(product_id)
JOIN users seller ON seller.user_id = p.seller_id
WHERE p.availability = 'available' AND p.visibility = 'visible'
  AND seller.status = 'active' AND seller.is_active
  AND r.assessment_state <> 'ready'
ORDER BY p.product_id;

-- 4. Seller's order history derives seller/terms from retained product/revision.
SELECT * FROM seller_order_history WHERE seller_id = 2
ORDER BY created_at DESC,transaction_id DESC LIMIT 20;

-- 5. Buyer's own orders and append-only transition history.
SELECT t.transaction_id,t.status,h.event_id,h.from_status,h.to_status,h.occurred_at
FROM transactions t JOIN order_status_history h USING(transaction_id)
WHERE t.buyer_id = 3
ORDER BY t.transaction_id,h.event_id;

-- 6. Participant-scoped conversation cursor; this WHERE is not a substitute
-- for authorization on the conversation/details/read-receipt endpoints.
SELECT m.message_id,m.sender_id,m.message_text,m.sent_at,m.read_at
FROM chat_messages m
JOIN conversations c USING(conversation_id)
JOIN products p ON p.product_id = c.product_id
WHERE c.conversation_id = 100 AND 3 IN (c.buyer_id,p.seller_id)
  AND m.message_id > 0
ORDER BY m.message_id LIMIT 50;

-- 7. Administrator-only queue: one listing per row, all open case targets retained.
SELECT * FROM admin_review_queue
ORDER BY priority_group,oldest_waiting_at,product_id LIMIT 50;

-- 8. Select the effective decision at export cutoff FIRST, then eligible labels.
-- Do not filter eligible_training_labels by cutoff after selecting today's result:
-- that loses a prior decision if a later correction lies beyond the cutoff.
WITH at_cutoff AS (
    SELECT * FROM effective_reviews_at(statement_timestamp())
)
SELECT r.product_id,r.revision_no,r.review_id,r.verdict AS label,
       r.reviewed_at AS label_decided_at,p.seller_id AS internal_seller_group_id
FROM at_cutoff r JOIN products p USING(product_id)
WHERE r.verdict IN ('fraud','legitimate')
  AND length(btrim(r.reason)) > 0 AND length(btrim(r.evidence_summary)) > 0
ORDER BY r.product_id,r.revision_no;
-- The exporter pseudonymizes grouping IDs and joins a time-eligible feature
-- snapshot. ALL labels from006_seed.sql must be marked synthetic in a dataset.

-- 9. Full prediction history does not imply that any result is currently valid.
SELECT * FROM risk_score_history WHERE product_id = 102
ORDER BY predicted_at DESC,risk_id DESC;

-- 10. Queue lookup plan, matching the worker's runnable-job selection.
-- Actual claims use the claim function in004 within a short write transaction.
EXPLAIN (ANALYZE,BUFFERS)
SELECT job_id FROM risk_scan_jobs
WHERE status = 'queued' AND retry_at <= clock_timestamp()
ORDER BY retry_at,job_id LIMIT 20;

-- 11. Recoverable campaign progress and stable event/product identities.
SELECT c.campaign_id,c.event_type,c.status,c.cursor_product_id,c.cutoff_product_id,
       count(e.product_id) AS processed_products
FROM risk_rescan_campaigns c
LEFT JOIN risk_rescan_events e USING(campaign_id)
GROUP BY c.campaign_id ORDER BY c.campaign_id;

-- 12. Store authoritative confusion counts; derive precision/recall/F1.
SELECT model_id,partition,slice_key,sample_count,
       true_positive::numeric / NULLIF(true_positive+false_positive,0) AS precision,
       true_positive::numeric / NULLIF(true_positive+false_negative,0) AS recall,
       2.0*true_positive / NULLIF(2*true_positive+false_positive+false_negative,0) AS f1,
       average_precision
FROM model_evaluations ORDER BY model_id,partition,slice_key;

-- A sequential scan is normal for this tiny seed. Record actual plans/timings
-- on the target workload (10,000 listings); these examples are not benchmarks.
