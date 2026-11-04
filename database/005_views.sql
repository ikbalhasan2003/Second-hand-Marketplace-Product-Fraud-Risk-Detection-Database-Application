-- Apply after 001..004. These internal read models do not authorize an end user.
BEGIN;

-- Resolve the canonical decision as it was known at a particular cutoff.
-- Filter by time BEFORE selecting the last decision, then test label eligibility.
CREATE FUNCTION effective_reviews_at(p_cutoff timestamptz)
RETURNS SETOF moderation_reviews LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (product_id,revision_no) r.*
    FROM moderation_reviews r
    WHERE r.reviewed_at <= p_cutoff
    ORDER BY product_id,revision_no,reviewed_at DESC,review_id DESC
$$;

CREATE VIEW latest_effective_reviews AS
SELECT * FROM effective_reviews_at(statement_timestamp());
COMMENT ON VIEW latest_effective_reviews IS
'Current canonical decision per revision, including unresolved corrections. Use effective_reviews_at(cutoff) for a historical export or historical seller evidence.';

CREATE VIEW eligible_training_labels AS
SELECT r.review_id,r.product_id,r.revision_no,p.seller_id,
       r.verdict AS label,
       CASE r.verdict WHEN 'fraud' THEN 1 ELSE 0 END AS fraud_class,
       'moderation_review'::text AS label_source,
       r.reviewed_at AS label_decided_at
FROM latest_effective_reviews r
JOIN products p USING (product_id)
WHERE r.verdict IN ('fraud','legitimate')
  AND length(btrim(r.reason)) > 0
  AND length(btrim(r.evidence_summary)) > 0;
COMMENT ON VIEW eligible_training_labels IS
'Internal candidate labels, not a complete dataset. Latest unresolved decisions exclude earlier labels. Exporters must check provenance, cutoff and feature time, pseudonymize grouping identifiers, and exclude private evidence.';

CREATE VIEW admin_review_queue AS
WITH open_reports AS (
    SELECT product_id,count(*) AS open_report_count,
           min(created_at) AS oldest_report_at,
           array_agg(DISTINCT revision_no ORDER BY revision_no) AS reported_revision_nos
    FROM fraud_reports
    WHERE status IN ('pending','reviewing')
    GROUP BY product_id
)
SELECT p.product_id,p.seller_id,p.current_revision_no,
       v.title,p.availability,p.visibility,
       r.assessment_state,r.risk_score,r.risk_level,
       COALESCE(o.open_report_count,0::bigint) AS open_report_count,
       o.oldest_report_at,
       COALESCE(o.reported_revision_nos,ARRAY[]::integer[]) AS reported_revision_nos,
       (COALESCE(r.assessment_state = 'ready' AND r.risk_level = 'high',false)) AS current_high_risk,
       CASE WHEN r.assessment_state = 'ready' AND r.risk_level = 'high' THEN 0 ELSE 1 END AS priority_group,
       COALESCE(o.oldest_report_at,r.feature_as_of,p.created_at) AS oldest_waiting_at
FROM products p
LEFT JOIN product_revisions v ON (v.product_id,v.revision_no) = (p.product_id,p.current_revision_no)
LEFT JOIN open_reports o ON o.product_id = p.product_id
LEFT JOIN current_listing_risk r ON r.product_id = p.product_id
WHERE o.product_id IS NOT NULL
   OR (r.assessment_state = 'ready' AND r.risk_level = 'high');
COMMENT ON VIEW admin_review_queue IS
'One row per listing, combining open report cases and current high-risk predictions. Reported revision numbers retain historical targets. An AI alert is not a confirmed report or verdict; only authorized administrators may read this view.';

CREATE VIEW seller_order_history AS
SELECT t.transaction_id,t.product_id,t.revision_no,p.seller_id,t.buyer_id,
       v.title AS ordered_title,v.price AS agreed_price,v.currency,
       t.status,t.created_at,t.updated_at,
       e.event_id AS latest_event_id,e.occurred_at AS latest_event_at
FROM transactions t
JOIN products p USING (product_id)
JOIN product_revisions v ON (v.product_id,v.revision_no) = (t.product_id,t.revision_no)
LEFT JOIN LATERAL (
    SELECT h.event_id,h.occurred_at
    FROM order_status_history h
    WHERE h.transaction_id = t.transaction_id
    ORDER BY h.event_id DESC LIMIT 1
) e ON true;
COMMENT ON VIEW seller_order_history IS
'One row per order, with terms from its immutable purchased revision. Caller queries must restrict seller_id to the authenticated seller; the view itself is not an access-control boundary.';

COMMIT;
