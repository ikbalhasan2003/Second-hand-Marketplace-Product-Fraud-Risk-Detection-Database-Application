ALTER TABLE transactions ADD COLUMN assessment_snapshot jsonb;

CREATE OR REPLACE FUNCTION guard_scanned_purchase() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE assessment record;
BEGIN
    SELECT * INTO assessment FROM current_listing_risk WHERE product_id=NEW.product_id;
    IF NOT FOUND OR assessment.assessment_state <> 'ready' THEN
        RAISE EXCEPTION 'A current successful assessment is required before purchase' USING ERRCODE='23514';
    END IF;
    NEW.assessment_snapshot := jsonb_build_object(
        'assessment_state',assessment.assessment_state,'risk_id',assessment.risk_id,
        'risk_score',assessment.risk_score,'risk_level',assessment.risk_level,
        'revision_no',NEW.revision_no,'feature_as_of',assessment.feature_as_of,
        'predicted_at',assessment.predicted_at,
        'evidence',(SELECT jsonb_build_object('observed_factors',h.observed_factors,
                     'model_id',h.model_id,'ruleset_id',h.ruleset_id)
                    FROM risk_score_history h WHERE h.risk_id=assessment.risk_id));
    RETURN NEW;
END $$;

CREATE FUNCTION guard_order_assessment_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.assessment_snapshot IS DISTINCT FROM OLD.assessment_snapshot THEN
        RAISE EXCEPTION 'Purchase assessment snapshot is immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER order_assessment_snapshot_immutable BEFORE UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION guard_order_assessment_snapshot();
REVOKE ALL ON FUNCTION guard_order_assessment_snapshot() FROM PUBLIC;
