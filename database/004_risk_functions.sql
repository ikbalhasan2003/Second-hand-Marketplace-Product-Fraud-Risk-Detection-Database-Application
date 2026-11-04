-- Apply after 003_core_functions.sql. Worker APIs use SECURITY DEFINER; deploy
-- with a non-login owner, trusted public schema, and EXECUTE-only worker grants.
BEGIN;
SET LOCAL TIME ZONE 'UTC';

CREATE FUNCTION reject_risk_history_change() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; create a new version/event', TG_TABLE_NAME;
END $$;
CREATE TRIGGER feature_schemas_immutable BEFORE UPDATE OR DELETE ON feature_schemas FOR EACH ROW EXECUTE FUNCTION reject_risk_history_change();
CREATE TRIGGER dataset_sources_immutable BEFORE UPDATE OR DELETE ON dataset_sources FOR EACH ROW EXECUTE FUNCTION reject_risk_history_change();
CREATE TRIGGER model_evaluations_immutable BEFORE UPDATE OR DELETE ON model_evaluations FOR EACH ROW EXECUTE FUNCTION reject_risk_history_change();
CREATE TRIGGER risk_logs_immutable BEFORE UPDATE OR DELETE ON risk_logs FOR EACH ROW EXECUTE FUNCTION reject_risk_history_change();
CREATE TRIGGER rescan_events_immutable BEFORE UPDATE OR DELETE ON risk_rescan_events FOR EACH ROW EXECUTE FUNCTION reject_risk_history_change();

CREATE FUNCTION guard_dataset_version() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM require_admin_actor(); PERFORM require_action_reason();
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Dataset versions are retained'; END IF;
    IF TG_OP='INSERT' THEN
        IF NEW.state<>'building' THEN RAISE EXCEPTION 'Create dataset as building; freeze through validated update'; END IF;
        IF NEW.created_by<>require_admin_actor() THEN RAISE EXCEPTION 'Dataset creator must be current administrator'; END IF;
        RETURN NEW;
    END IF;
    IF OLD.state = 'frozen' THEN RAISE EXCEPTION 'Frozen dataset is immutable'; END IF;
    IF NEW.dataset_id <> OLD.dataset_id THEN RAISE EXCEPTION 'Dataset identity is immutable'; END IF;
    IF (NEW.created_by,NEW.created_at) IS DISTINCT FROM (OLD.created_by,OLD.created_at) THEN RAISE EXCEPTION 'Dataset creation facts are immutable'; END IF;
    IF NEW.state = 'frozen' THEN
        IF EXISTS (
            SELECT 1 FROM dataset_records a JOIN dataset_records b
              ON a.dataset_id=b.dataset_id AND a.record_id < b.record_id
             AND (a.seller_group_key=b.seller_group_key
                  OR a.template_family_key=b.template_family_key
                  OR a.duplicate_group_key=b.duplicate_group_key)
            JOIN dataset_split_groups ga ON ga.dataset_id=a.dataset_id AND ga.split_group_id=a.split_group_id
            JOIN dataset_split_groups gb ON gb.dataset_id=b.dataset_id AND gb.split_group_id=b.split_group_id
            WHERE a.dataset_id=NEW.dataset_id AND ga.partition <> gb.partition
        ) THEN RAISE EXCEPTION 'Related seller/template/duplicate records cross dataset partitions'; END IF;
        IF EXISTS (SELECT 1 FROM dataset_records WHERE dataset_id=NEW.dataset_id AND label_decided_at>NEW.export_cutoff) THEN
            RAISE EXCEPTION 'Dataset contains labels known after export cutoff';
        END IF;
        IF EXISTS (
            SELECT 1 FROM dataset_records d JOIN dataset_sources s ON s.source_id=d.source_id
            LEFT JOIN LATERAL (
                SELECT r.* FROM moderation_reviews r WHERE r.product_id=d.product_id AND r.revision_no=d.revision_no
                  AND r.reviewed_at<=NEW.export_cutoff ORDER BY r.reviewed_at DESC,r.review_id DESC LIMIT 1
            ) effective ON TRUE
            WHERE d.dataset_id=NEW.dataset_id AND s.source_type='project_review'
              AND (effective.review_id IS DISTINCT FROM d.review_id OR effective.verdict IS DISTINCT FROM d.label
                   OR effective.verdict NOT IN ('fraud','legitimate') OR length(btrim(effective.evidence_summary))=0)
        ) THEN RAISE EXCEPTION 'Project labels must remain latest eligible decisions at freeze cutoff'; END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER dataset_versions_guard BEFORE INSERT OR UPDATE OR DELETE ON dataset_versions FOR EACH ROW EXECUTE FUNCTION guard_dataset_version();

CREATE FUNCTION audit_dataset_export() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.state='frozen' AND OLD.state='building' THEN
        INSERT INTO admin_audit_logs(admin_id,action_type,dataset_id,reason,before_data,after_data)
        VALUES(require_admin_actor(),'dataset_export',NEW.dataset_id,require_action_reason(),
               jsonb_build_object('state',OLD.state),jsonb_build_object('state',NEW.state,'dataset_sha256',NEW.dataset_sha256));
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER dataset_export_audit AFTER UPDATE ON dataset_versions FOR EACH ROW EXECUTE FUNCTION audit_dataset_export();

CREATE FUNCTION guard_dataset_child() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_dataset BIGINT; v_state TEXT; v_review moderation_reviews%ROWTYPE; v_source TEXT;
BEGIN
    IF TG_OP <> 'INSERT' THEN v_dataset:=OLD.dataset_id; ELSE v_dataset:=NEW.dataset_id; END IF;
    SELECT state INTO v_state FROM dataset_versions WHERE dataset_id=v_dataset FOR SHARE;
    IF v_state <> 'building' THEN RAISE EXCEPTION 'Frozen dataset contents cannot change'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    IF TG_OP='UPDATE' AND NEW.dataset_id<>OLD.dataset_id THEN RAISE EXCEPTION 'Cannot move dataset children'; END IF;
    IF TG_TABLE_NAME='dataset_records' THEN
        SELECT source_type INTO v_source FROM dataset_sources WHERE source_id=NEW.source_id;
        IF (v_source='synthetic') <> NEW.is_synthetic THEN RAISE EXCEPTION 'Synthetic provenance mismatch'; END IF;
        IF v_source='project_review' THEN
            SELECT * INTO v_review FROM moderation_reviews WHERE review_id=NEW.review_id;
            IF NOT FOUND OR v_review.verdict<>NEW.label OR length(btrim(v_review.evidence_summary))=0
               OR v_review.product_id IS DISTINCT FROM NEW.product_id OR v_review.revision_no IS DISTINCT FROM NEW.revision_no
               OR v_review.reviewed_at IS DISTINCT FROM NEW.label_decided_at THEN
                RAISE EXCEPTION 'Project label must match its evidence-backed target review';
            END IF;
            IF EXISTS (SELECT 1 FROM moderation_reviews r JOIN dataset_versions d ON d.dataset_id=NEW.dataset_id
                       WHERE r.product_id=NEW.product_id AND r.revision_no=NEW.revision_no
                         AND r.reviewed_at<=d.export_cutoff AND r.reviewed_at>v_review.reviewed_at) THEN
                RAISE EXCEPTION 'Export must use latest decision as known at cutoff, including unresolved corrections';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER dataset_records_guard BEFORE INSERT OR UPDATE OR DELETE ON dataset_records FOR EACH ROW EXECUTE FUNCTION guard_dataset_child();
CREATE TRIGGER dataset_groups_guard BEFORE INSERT OR UPDATE OR DELETE ON dataset_split_groups FOR EACH ROW EXECUTE FUNCTION guard_dataset_child();

CREATE FUNCTION guard_risk_configuration() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_actor BIGINT; v_medium NUMERIC; v_high NUMERIC; v_dataset dataset_versions%ROWTYPE;
BEGIN
    v_actor:=require_admin_actor(); PERFORM require_action_reason();
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Risk configuration versions are retained'; END IF;
    IF TG_TABLE_NAME='risk_models' THEN
        IF TG_OP='INSERT' THEN
            IF NEW.registered_by<>v_actor THEN RAISE EXCEPTION 'Model registrar must be current administrator'; END IF;
            IF NEW.state<>'registered' THEN RAISE EXCEPTION 'Register a model before activation'; END IF;
            SELECT * INTO v_dataset FROM dataset_versions WHERE dataset_id=NEW.dataset_id;
            IF v_dataset.state<>'frozen' OR v_dataset.feature_schema_id<>NEW.feature_schema_id THEN
                RAISE EXCEPTION 'Model requires frozen compatible dataset';
            END IF;
        ELSIF (to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state') THEN
            RAISE EXCEPTION 'Registered model metadata/artifact is immutable';
        END IF;
        IF TG_OP='UPDATE' AND NEW.state IS DISTINCT FROM OLD.state THEN
            v_actor:=require_admin_actor(); PERFORM require_action_reason();
            IF NEW.state='registered' THEN RAISE EXCEPTION 'Cannot return to registered state'; END IF;
            IF NEW.state='active' AND NOT EXISTS(SELECT 1 FROM model_evaluations WHERE model_id=NEW.model_id AND partition='validation') THEN
                RAISE EXCEPTION 'Activation requires recorded validation evaluation';
            END IF;
        END IF;
    ELSE
        IF TG_OP='INSERT' THEN
            IF NEW.state<>'draft' THEN RAISE EXCEPTION 'Create ruleset as draft'; END IF;
            IF NEW.created_by<>v_actor THEN RAISE EXCEPTION 'Ruleset creator must be current administrator'; END IF;
        END IF;
        IF TG_OP='UPDATE' AND (NEW.ruleset_id,NEW.created_by,NEW.created_at) IS DISTINCT FROM (OLD.ruleset_id,OLD.created_by,OLD.created_at) THEN
            RAISE EXCEPTION 'Ruleset creation facts are immutable';
        END IF;
        IF TG_OP='UPDATE' AND OLD.published_at IS NOT NULL AND
            (to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state') THEN
            RAISE EXCEPTION 'Published ruleset metadata is immutable';
        END IF;
        IF TG_OP='UPDATE' AND NEW.state IS DISTINCT FROM OLD.state THEN
            v_actor:=require_admin_actor(); PERFORM require_action_reason();
            IF NEW.state='draft' THEN RAISE EXCEPTION 'Cannot unpublish ruleset'; END IF;
            IF OLD.state='draft' AND NEW.state<>'active' THEN RAISE EXCEPTION 'Publish draft by activating it'; END IF;
            IF NEW.state='active' THEN
                SELECT numeric_value INTO v_medium FROM risk_rules WHERE ruleset_id=NEW.ruleset_id AND rule_key='medium_min';
                SELECT numeric_value INTO v_high FROM risk_rules WHERE ruleset_id=NEW.ruleset_id AND rule_key='high_min';
                IF v_medium IS NULL OR v_high IS NULL OR NOT (0<=v_medium AND v_medium<v_high AND v_high<=100)
                   OR trunc(v_medium)<>v_medium OR trunc(v_high)<>v_high THEN
                    RAISE EXCEPTION 'Rules require integer 0 <= medium_min < high_min <= 100';
                END IF;
                IF OLD.published_at IS NULL THEN NEW.published_at:=clock_timestamp(); NEW.published_by:=v_actor; END IF;
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER risk_models_guard BEFORE INSERT OR UPDATE OR DELETE ON risk_models FOR EACH ROW EXECUTE FUNCTION guard_risk_configuration();
CREATE TRIGGER risk_rulesets_guard BEFORE INSERT OR UPDATE OR DELETE ON risk_rulesets FOR EACH ROW EXECUTE FUNCTION guard_risk_configuration();

CREATE FUNCTION guard_published_risk_rule() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_id BIGINT; v_time TIMESTAMPTZ;
BEGIN
    PERFORM require_admin_actor(); PERFORM require_action_reason();
    IF TG_OP='INSERT' THEN v_id:=NEW.ruleset_id; ELSE v_id:=OLD.ruleset_id; END IF;
    SELECT published_at INTO v_time FROM risk_rulesets WHERE ruleset_id=v_id FOR SHARE;
    IF v_time IS NOT NULL THEN RAISE EXCEPTION 'Published rule contents are immutable'; END IF;
    IF TG_OP='UPDATE' AND NEW.ruleset_id<>OLD.ruleset_id THEN RAISE EXCEPTION 'Cannot move rules between versions'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER risk_rules_guard BEFORE INSERT OR UPDATE OR DELETE ON risk_rules FOR EACH ROW EXECUTE FUNCTION guard_published_risk_rule();

CREATE FUNCTION check_active_risk_compatibility() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS(SELECT 1 FROM risk_models m CROSS JOIN risk_rulesets r WHERE m.state='active' AND r.state='active'
              AND m.feature_schema_id<>r.feature_schema_id) THEN RAISE EXCEPTION 'Active model/ruleset feature schemas differ'; END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER risk_model_compatibility AFTER INSERT OR UPDATE ON risk_models DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_active_risk_compatibility();
CREATE CONSTRAINT TRIGGER risk_ruleset_compatibility AFTER INSERT OR UPDATE ON risk_rulesets DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_active_risk_compatibility();

CREATE FUNCTION audit_risk_configuration() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.state IS NOT DISTINCT FROM OLD.state THEN RETURN NEW; END IF;
    IF TG_TABLE_NAME='risk_models' THEN
        INSERT INTO admin_audit_logs(admin_id,action_type,model_id,reason,before_data,after_data)
        VALUES(require_admin_actor(),'model_activation',NEW.model_id,require_action_reason(),jsonb_build_object('state',OLD.state),jsonb_build_object('state',NEW.state));
    ELSE
        INSERT INTO admin_audit_logs(admin_id,action_type,ruleset_id,reason,before_data,after_data)
        VALUES(require_admin_actor(),'ruleset_publication',NEW.ruleset_id,require_action_reason(),jsonb_build_object('state',OLD.state),jsonb_build_object('state',NEW.state));
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER risk_models_audit AFTER UPDATE ON risk_models FOR EACH ROW EXECUTE FUNCTION audit_risk_configuration();
CREATE TRIGGER risk_rulesets_audit AFTER UPDATE ON risk_rulesets FOR EACH ROW EXECUTE FUNCTION audit_risk_configuration();

CREATE FUNCTION activate_risk_configuration(p_model BIGINT,p_ruleset BIGINT) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_schema BIGINT;
BEGIN
    PERFORM require_admin_actor(); PERFORM require_action_reason();
    PERFORM pg_advisory_xact_lock(719241,1);
    SELECT feature_schema_id INTO v_schema FROM risk_models WHERE model_id=p_model FOR UPDATE;
    IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM risk_rulesets WHERE ruleset_id=p_ruleset AND feature_schema_id=v_schema) THEN
        RAISE EXCEPTION 'Unknown/incompatible model and ruleset';
    END IF;
    UPDATE risk_models SET state='retired' WHERE state='active' AND model_id<>p_model;
    UPDATE risk_rulesets SET state='retired' WHERE state='active' AND ruleset_id<>p_ruleset;
    UPDATE risk_models SET state='active' WHERE model_id=p_model;
    UPDATE risk_rulesets SET state='active' WHERE ruleset_id=p_ruleset;
END $$;

CREATE FUNCTION enqueue_product_scan(p_product BIGINT) RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_product products%ROWTYPE; v_model BIGINT; v_rules BIGINT; v_schema BIGINT; v_job BIGINT;
BEGIN
    SELECT * INTO v_product FROM products WHERE product_id=p_product;
    IF NOT FOUND OR v_product.current_revision_no IS NULL OR v_product.first_published_at IS NULL THEN RETURN NULL; END IF;
    SELECT m.model_id,r.ruleset_id,m.feature_schema_id INTO v_model,v_rules,v_schema
      FROM risk_models m JOIN risk_rulesets r ON r.feature_schema_id=m.feature_schema_id WHERE m.state='active' AND r.state='active';
    INSERT INTO risk_scan_jobs(product_id,revision_no,context_version,model_id,ruleset_id,feature_schema_id)
    VALUES(p_product,v_product.current_revision_no,v_product.context_version,v_model,v_rules,v_schema)
    ON CONFLICT DO NOTHING RETURNING job_id INTO v_job;
    IF v_job IS NULL THEN
        SELECT job_id INTO v_job FROM risk_scan_jobs WHERE product_id=p_product AND revision_no=v_product.current_revision_no
          AND context_version=v_product.context_version AND model_id IS NOT DISTINCT FROM v_model AND ruleset_id IS NOT DISTINCT FROM v_rules;
    END IF;
    RETURN v_job;
END $$;

CREATE FUNCTION queue_product_revision() RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
    IF NEW.first_published_at IS NOT NULL AND NEW.current_revision_no IS NOT NULL AND
       (TG_OP='INSERT' OR OLD.first_published_at IS NULL OR NEW.current_revision_no IS DISTINCT FROM OLD.current_revision_no
        OR NEW.context_version IS DISTINCT FROM OLD.context_version) THEN
        PERFORM enqueue_product_scan(NEW.product_id);
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER products_queue_risk AFTER INSERT OR UPDATE ON products FOR EACH ROW EXECUTE FUNCTION queue_product_revision();

CREATE FUNCTION guard_risk_job() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Scan jobs are retained'; END IF;
    IF TG_OP='INSERT' THEN
        IF NEW.status<>'queued' OR NEW.attempts<>0 OR NEW.feature_snapshot IS NOT NULL THEN
            RAISE EXCEPTION 'New job must start queued without an inference snapshot';
        END IF;
        IF NEW.model_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM risk_models m JOIN risk_rulesets r ON r.ruleset_id=NEW.ruleset_id
              WHERE m.model_id=NEW.model_id AND m.feature_schema_id=NEW.feature_schema_id AND r.feature_schema_id=NEW.feature_schema_id) THEN
            RAISE EXCEPTION 'Job configuration feature schemas differ';
        END IF;
        RETURN NEW;
    END IF;
    IF (NEW.job_id,NEW.product_id,NEW.revision_no,NEW.context_version,NEW.created_at) IS DISTINCT FROM
       (OLD.job_id,OLD.product_id,OLD.revision_no,OLD.context_version,OLD.created_at) THEN RAISE EXCEPTION 'Job identity and target are immutable'; END IF;
    IF OLD.status IN ('succeeded','failed','superseded') THEN RAISE EXCEPTION 'Terminal job is immutable'; END IF;
    IF OLD.model_id IS NOT NULL AND (NEW.model_id,NEW.ruleset_id,NEW.feature_schema_id) IS DISTINCT FROM
       (OLD.model_id,OLD.ruleset_id,OLD.feature_schema_id) THEN RAISE EXCEPTION 'Bound job configuration is immutable'; END IF;
    IF OLD.source_event_key IS NOT NULL AND NEW.source_event_key IS DISTINCT FROM OLD.source_event_key THEN RAISE EXCEPTION 'Source event is immutable'; END IF;
    IF OLD.feature_snapshot IS NOT NULL AND (NEW.feature_as_of,NEW.feature_snapshot) IS DISTINCT FROM
       (OLD.feature_as_of,OLD.feature_snapshot) THEN RAISE EXCEPTION 'Persisted feature snapshot is immutable'; END IF;
    IF NEW.model_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM risk_models m JOIN risk_rulesets r ON r.ruleset_id=NEW.ruleset_id
          WHERE m.model_id=NEW.model_id AND m.feature_schema_id=NEW.feature_schema_id AND r.feature_schema_id=NEW.feature_schema_id) THEN
        RAISE EXCEPTION 'Job configuration feature schemas differ';
    END IF;
    NEW.updated_at:=clock_timestamp();
    RETURN NEW;
END $$;
CREATE TRIGGER risk_jobs_guard BEFORE INSERT OR UPDATE OR DELETE ON risk_scan_jobs FOR EACH ROW EXECUTE FUNCTION guard_risk_job();

CREATE FUNCTION claim_risk_job(p_lease INTERVAL DEFAULT INTERVAL '2 minutes') RETURNS SETOF risk_scan_jobs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE j risk_scan_jobs%ROWTYPE; v_model BIGINT; v_rules BIGINT; v_schema BIGINT;
BEGIN
    IF p_lease<=INTERVAL '0' OR p_lease>INTERVAL '10 minutes' THEN RAISE EXCEPTION 'Lease must be between zero and ten minutes'; END IF;
    SELECT m.model_id,r.ruleset_id,m.feature_schema_id INTO v_model,v_rules,v_schema
      FROM risk_models m JOIN risk_rulesets r ON r.feature_schema_id=m.feature_schema_id WHERE m.state='active' AND r.state='active';
    LOOP
        SELECT * INTO j FROM risk_scan_jobs
         WHERE ((status='queued' AND retry_at<=clock_timestamp() AND (model_id IS NOT NULL OR v_model IS NOT NULL))
             OR (status='processing' AND lease_expires_at<=clock_timestamp()))
         ORDER BY retry_at,job_id FOR UPDATE SKIP LOCKED LIMIT 1;
        IF NOT FOUND THEN RETURN; END IF;
        IF j.attempts>=3 THEN
            UPDATE risk_scan_jobs SET status='failed',claim_token=NULL,lease_expires_at=NULL,error_code='attempts_exhausted',completed_at=clock_timestamp() WHERE job_id=j.job_id;
            CONTINUE;
        END IF;
        IF j.model_id IS NULL THEN
            BEGIN
                UPDATE risk_scan_jobs SET model_id=v_model,ruleset_id=v_rules,feature_schema_id=v_schema WHERE job_id=j.job_id;
            EXCEPTION WHEN unique_violation THEN
                UPDATE risk_scan_jobs SET status='superseded',completed_at=clock_timestamp(),error_code='coalesced_existing_bound_job' WHERE job_id=j.job_id;
                CONTINUE;
            END;
        END IF;
        RETURN QUERY UPDATE risk_scan_jobs SET status='processing',attempts=attempts+1,claim_token=gen_random_uuid(),
          lease_expires_at=clock_timestamp()+p_lease,error_code=NULL WHERE job_id=j.job_id RETURNING *;
        RETURN;
    END LOOP;
END $$;

CREATE FUNCTION locked_risk_claim(p_job BIGINT,p_token UUID) RETURNS risk_scan_jobs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE j risk_scan_jobs%ROWTYPE;
BEGIN
    SELECT * INTO j FROM risk_scan_jobs WHERE job_id=p_job FOR UPDATE;
    IF NOT FOUND OR j.status<>'processing' OR j.claim_token IS DISTINCT FROM p_token OR j.lease_expires_at<=clock_timestamp() THEN
        RAISE EXCEPTION 'Expired/replaced/invalid job claim' USING ERRCODE='55000';
    END IF;
    RETURN j;
END $$;

CREATE FUNCTION save_risk_snapshot(p_job BIGINT,p_token UUID,p_as_of TIMESTAMPTZ,p_snapshot JSONB) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE j risk_scan_jobs%ROWTYPE;
BEGIN
    j:=locked_risk_claim(p_job,p_token);
    IF p_as_of IS NULL OR p_snapshot IS NULL OR p_as_of>clock_timestamp() OR jsonb_typeof(p_snapshot)<>'object' THEN RAISE EXCEPTION 'Invalid feature snapshot'; END IF;
    IF j.feature_snapshot IS NOT NULL THEN
        IF j.feature_as_of IS DISTINCT FROM p_as_of OR j.feature_snapshot IS DISTINCT FROM p_snapshot THEN RAISE EXCEPTION 'Retry must reuse frozen features'; END IF;
        RETURN;
    END IF;
    UPDATE risk_scan_jobs SET feature_as_of=p_as_of,feature_snapshot=p_snapshot
      WHERE job_id=p_job AND claim_token=p_token AND lease_expires_at>clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'Claim expired while persisting features' USING ERRCODE='55000'; END IF;
END $$;

CREATE FUNCTION heartbeat_risk_job(p_job BIGINT,p_token UUID,p_lease INTERVAL DEFAULT INTERVAL '2 minutes') RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
    PERFORM locked_risk_claim(p_job,p_token);
    IF p_lease<=INTERVAL '0' OR p_lease>INTERVAL '10 minutes' THEN RAISE EXCEPTION 'Invalid lease interval'; END IF;
    UPDATE risk_scan_jobs SET lease_expires_at=clock_timestamp()+p_lease
      WHERE job_id=p_job AND claim_token=p_token AND lease_expires_at>clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'Claim expired before heartbeat' USING ERRCODE='55000'; END IF;
END $$;

CREATE FUNCTION fail_risk_job(p_job BIGINT,p_token UUID,p_error_code VARCHAR,p_retryable BOOLEAN DEFAULT TRUE) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE j risk_scan_jobs%ROWTYPE;
BEGIN
    j:=locked_risk_claim(p_job,p_token);
    IF p_error_code IS NULL OR p_error_code !~ '^[a-z0-9_]{1,80}$' THEN RAISE EXCEPTION 'Use a sanitized error code'; END IF;
    UPDATE risk_scan_jobs SET status=CASE WHEN p_retryable AND j.attempts<3 THEN 'queued' ELSE 'failed' END,
      claim_token=NULL,lease_expires_at=NULL,error_code=p_error_code,
      retry_at=clock_timestamp()+make_interval(secs=>power(2,j.attempts)::INTEGER),
      completed_at=CASE WHEN p_retryable AND j.attempts<3 THEN NULL ELSE clock_timestamp() END
      WHERE job_id=p_job AND claim_token=p_token AND lease_expires_at>clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'Claim expired before failure write' USING ERRCODE='55000'; END IF;
END $$;

CREATE FUNCTION complete_risk_job(p_job BIGINT,p_token UUID,p_score INTEGER,p_factors JSONB DEFAULT '[]',p_explanation JSONB DEFAULT NULL) RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE j risk_scan_jobs%ROWTYPE; v_medium NUMERIC; v_high NUMERIC; v_id BIGINT;
BEGIN
    j:=locked_risk_claim(p_job,p_token);
    IF j.feature_snapshot IS NULL THEN RAISE EXCEPTION 'Persist feature snapshot before inference completion'; END IF;
    SELECT numeric_value INTO v_medium FROM risk_rules WHERE ruleset_id=j.ruleset_id AND rule_key='medium_min';
    SELECT numeric_value INTO v_high FROM risk_rules WHERE ruleset_id=j.ruleset_id AND rule_key='high_min';
    INSERT INTO risk_logs(job_id,risk_score,risk_level,observed_factors,model_explanation)
    VALUES(p_job,p_score,CASE WHEN p_score>=v_high THEN 'high' WHEN p_score>=v_medium THEN 'medium' ELSE 'low' END,p_factors,p_explanation)
    RETURNING risk_id INTO v_id;
    UPDATE risk_scan_jobs SET status='succeeded',claim_token=NULL,lease_expires_at=NULL,completed_at=clock_timestamp()
      WHERE job_id=p_job AND claim_token=p_token AND lease_expires_at>clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'Claim expired before completion' USING ERRCODE='55000'; END IF;
    RETURN v_id;
END $$;

CREATE FUNCTION validate_risk_result() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE j risk_scan_jobs%ROWTYPE; v_medium NUMERIC; v_high NUMERIC;
BEGIN
    SELECT * INTO j FROM risk_scan_jobs WHERE job_id=NEW.job_id;
    IF j.status<>'processing' OR j.feature_snapshot IS NULL OR j.lease_expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'Result requires live processing job and frozen snapshot'; END IF;
    SELECT numeric_value INTO v_medium FROM risk_rules WHERE ruleset_id=j.ruleset_id AND rule_key='medium_min';
    SELECT numeric_value INTO v_high FROM risk_rules WHERE ruleset_id=j.ruleset_id AND rule_key='high_min';
    IF v_medium IS NULL OR v_high IS NULL OR NEW.risk_level<>(CASE WHEN NEW.risk_score>=v_high THEN 'high' WHEN NEW.risk_score>=v_medium THEN 'medium' ELSE 'low' END) THEN
        RAISE EXCEPTION 'Risk level does not match pinned ruleset';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER risk_result_guard BEFORE INSERT ON risk_logs FOR EACH ROW EXECUTE FUNCTION validate_risk_result();

CREATE FUNCTION check_job_result_consistency() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_job BIGINT; v_status TEXT; v_exists BOOLEAN;
BEGIN
    IF TG_TABLE_NAME='risk_logs' THEN v_job:=NEW.job_id; ELSE v_job:=NEW.job_id; END IF;
    SELECT status INTO v_status FROM risk_scan_jobs WHERE job_id=v_job;
    SELECT EXISTS(SELECT 1 FROM risk_logs WHERE job_id=v_job) INTO v_exists;
    IF (v_status='succeeded') IS DISTINCT FROM v_exists THEN RAISE EXCEPTION 'Succeeded job and result must commit together'; END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER jobs_result_consistency AFTER INSERT OR UPDATE ON risk_scan_jobs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_job_result_consistency();
CREATE CONSTRAINT TRIGGER results_job_consistency AFTER INSERT ON risk_logs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_job_result_consistency();

CREATE FUNCTION campaign_from_audit() RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_type TEXT; v_seller BIGINT; v_target BIGINT; v_cutoff BIGINT; v_key TEXT;
BEGIN
    v_key:='audit:'||NEW.audit_id;
    IF NEW.action_type IN ('model_activation','ruleset_publication') THEN
        IF NEW.after_data->>'state'<>'active' THEN RETURN NEW; END IF;
        v_type:=NEW.action_type;
    ELSIF NEW.action_type='moderation_decision' THEN
        v_type:='seller_evidence';
        SELECT p.seller_id INTO v_seller FROM products p JOIN moderation_reviews r ON r.product_id=p.product_id WHERE r.review_id=NEW.review_id;
        IF v_seller IS NULL THEN RAISE EXCEPTION 'Moderation audit missing revision target'; END IF;
    ELSIF NEW.action_type='manual_rescan' THEN
        v_type:='manual_rescan'; v_target:=NEW.product_id;
        IF v_target IS NULL OR NEW.after_data->>'request_key' IS NULL THEN RAISE EXCEPTION 'Manual rescan needs product and request key'; END IF;
        v_key:='manual:'||(NEW.after_data->>'request_key');
    ELSE RETURN NEW;
    END IF;
    SELECT coalesce(max(product_id),0) INTO v_cutoff FROM products;
    INSERT INTO risk_rescan_campaigns(source_event_key,event_type,source_audit_id,seller_id,target_product_id,cutoff_product_id)
      VALUES(v_key,v_type,NEW.audit_id,v_seller,v_target,v_cutoff) ON CONFLICT DO NOTHING;
    RETURN NEW;
END $$;
CREATE TRIGGER audit_create_rescan_campaign AFTER INSERT ON admin_audit_logs FOR EACH ROW EXECUTE FUNCTION campaign_from_audit();

CREATE FUNCTION request_risk_rescan(p_product BIGINT,p_request UUID) RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_id BIGINT; v_product BIGINT;
BEGIN
    PERFORM require_admin_actor(); PERFORM require_action_reason();
    IF p_request IS NULL THEN RAISE EXCEPTION 'Rescan request key is required'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('manual-rescan:'||p_request::TEXT,0));
    SELECT campaign_id,target_product_id INTO v_id,v_product FROM risk_rescan_campaigns WHERE source_event_key='manual:'||p_request::TEXT;
    IF FOUND THEN
        IF v_product IS DISTINCT FROM p_product THEN RAISE EXCEPTION 'Rescan idempotency key reused with different product'; END IF;
        RETURN v_id;
    END IF;
    IF NOT EXISTS(SELECT 1 FROM products WHERE product_id=p_product AND first_published_at IS NOT NULL) THEN
        RAISE EXCEPTION 'A published product is required';
    END IF;
    INSERT INTO admin_audit_logs(admin_id,action_type,product_id,reason,after_data)
    VALUES(require_admin_actor(),'manual_rescan',p_product,require_action_reason(),jsonb_build_object('request_key',p_request));
    SELECT campaign_id INTO v_id FROM risk_rescan_campaigns WHERE source_event_key='manual:'||p_request::TEXT;
    RETURN v_id;
END $$;

CREATE FUNCTION create_daily_rescan(p_date DATE,p_timezone TEXT DEFAULT NULL) RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_id BIGINT; v_timezone TEXT;
BEGIN
    v_timezone:=coalesce(p_timezone,(SELECT refresh_timezone FROM marketplace_settings WHERE singleton));
    IF p_date IS NULL OR NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=v_timezone) THEN RAISE EXCEPTION 'Explicit valid date and configured timezone required'; END IF;
    INSERT INTO risk_rescan_campaigns(source_event_key,event_type,cutoff_product_id,refresh_date,refresh_timezone)
    SELECT 'daily:'||p_date::TEXT||':'||v_timezone,'daily_refresh',coalesce(max(product_id),0),p_date,v_timezone FROM products
    ON CONFLICT(source_event_key) DO NOTHING RETURNING campaign_id INTO v_id;
    IF v_id IS NULL THEN SELECT campaign_id INTO v_id FROM risk_rescan_campaigns WHERE source_event_key='daily:'||p_date::TEXT||':'||v_timezone; END IF;
    RETURN v_id;
END $$;

CREATE FUNCTION run_rescan_batch(p_campaign BIGINT,p_limit INTEGER DEFAULT 100) RETURNS INTEGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE c risk_rescan_campaigns%ROWTYPE; p products%ROWTYPE; v_job BIGINT; v_count INTEGER:=0; v_cursor BIGINT;
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>1000 THEN RAISE EXCEPTION 'Batch size must be 1..1000'; END IF;
    SELECT * INTO c FROM risk_rescan_campaigns WHERE campaign_id=p_campaign FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Unknown campaign'; END IF;
    IF c.status='completed' THEN RETURN 0; END IF;
    v_cursor:=c.cursor_product_id;
    UPDATE risk_rescan_campaigns SET status='processing',attempts=attempts+1,error_code=NULL WHERE campaign_id=p_campaign;
    FOR p IN SELECT * FROM products WHERE product_id>c.cursor_product_id AND product_id<=c.cutoff_product_id
        AND (c.seller_id IS NULL OR seller_id=c.seller_id) AND (c.target_product_id IS NULL OR product_id=c.target_product_id)
        ORDER BY product_id LIMIT p_limit FOR UPDATE
    LOOP
        v_cursor:=p.product_id;
        IF p.availability='available' AND p.first_published_at IS NOT NULL AND p.current_revision_no IS NOT NULL
           AND NOT EXISTS(SELECT 1 FROM risk_rescan_events WHERE campaign_id=p_campaign AND product_id=p.product_id) THEN
            UPDATE products SET context_version=context_version+1 WHERE product_id=p.product_id;
            v_job:=enqueue_product_scan(p.product_id);
            UPDATE risk_scan_jobs SET source_event_key=c.source_event_key||':product:'||p.product_id WHERE job_id=v_job AND source_event_key IS NULL;
            INSERT INTO risk_rescan_events(campaign_id,product_id,job_id) VALUES(p_campaign,p.product_id,v_job);
            v_count:=v_count+1;
        END IF;
    END LOOP;
    IF NOT EXISTS(SELECT 1 FROM products WHERE product_id>v_cursor AND product_id<=c.cutoff_product_id
                  AND (c.seller_id IS NULL OR seller_id=c.seller_id) AND (c.target_product_id IS NULL OR product_id=c.target_product_id)) THEN
        UPDATE risk_rescan_campaigns SET cursor_product_id=cutoff_product_id,status='completed',completed_at=clock_timestamp() WHERE campaign_id=p_campaign;
    ELSE UPDATE risk_rescan_campaigns SET cursor_product_id=v_cursor WHERE campaign_id=p_campaign;
    END IF;
    RETURN v_count;
END $$;

CREATE FUNCTION guard_rescan_campaign() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Rescan campaigns are retained'; END IF;
    IF (to_jsonb(NEW)-ARRAY['status','cursor_product_id','attempts','error_code','completed_at']) IS DISTINCT FROM
       (to_jsonb(OLD)-ARRAY['status','cursor_product_id','attempts','error_code','completed_at']) THEN RAISE EXCEPTION 'Campaign scope/cutoff is immutable'; END IF;
    IF NEW.cursor_product_id<OLD.cursor_product_id THEN RAISE EXCEPTION 'Campaign cursor cannot move backward'; END IF;
    IF OLD.status='completed' AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'Completed campaign is immutable'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER rescan_campaign_guard BEFORE UPDATE OR DELETE ON risk_rescan_campaigns FOR EACH ROW EXECUTE FUNCTION guard_rescan_campaign();

CREATE VIEW risk_score_history AS
SELECT l.risk_id,j.job_id,j.product_id,j.revision_no,j.context_version,j.model_id,j.ruleset_id,j.feature_schema_id,
       j.feature_as_of,l.risk_score,l.risk_level,l.observed_factors,l.model_explanation,l.predicted_at
FROM risk_logs l JOIN risk_scan_jobs j ON j.job_id=l.job_id;
CREATE VIEW fraud_logs AS SELECT * FROM risk_score_history WHERE risk_level='high';
COMMENT ON VIEW fraud_logs IS 'Compatibility name: high-risk AI observations, not proven fraud. Confirmed labels come from moderation decisions.';

CREATE VIEW current_listing_risk AS
SELECT p.product_id,p.current_revision_no AS revision_no,p.context_version,
       CASE WHEN ready.risk_id IS NOT NULL THEN 'ready'
            WHEN current_work.status='processing' AND current_work.lease_expires_at>clock_timestamp() THEN 'scanning'
            WHEN current_work.status IN ('queued','processing') THEN 'pending'
            WHEN current_work.status='failed' THEN 'failed'
            WHEN EXISTS(SELECT 1 FROM risk_score_history h WHERE h.product_id=p.product_id) THEN 'stale'
            ELSE 'pending' END AS assessment_state,
       ready.risk_id,ready.risk_score,ready.risk_level,ready.feature_as_of,ready.predicted_at
FROM products p
LEFT JOIN LATERAL (
    SELECT h.* FROM risk_score_history h JOIN risk_scan_jobs j ON j.job_id=h.job_id
    JOIN risk_models m ON m.model_id=j.model_id AND m.state='active'
    JOIN risk_rulesets r ON r.ruleset_id=j.ruleset_id AND r.state='active'
    WHERE h.product_id=p.product_id AND h.revision_no=p.current_revision_no AND h.context_version=p.context_version
      AND j.status='succeeded' AND j.feature_schema_id=m.feature_schema_id AND j.feature_schema_id=r.feature_schema_id
      AND j.feature_as_of>=clock_timestamp()-r.max_assessment_age AND j.feature_as_of<=clock_timestamp()
    ORDER BY h.risk_id DESC LIMIT 1
) ready ON TRUE
LEFT JOIN LATERAL (
    SELECT j.status,j.lease_expires_at FROM risk_scan_jobs j
    LEFT JOIN risk_models m ON m.model_id=j.model_id AND m.state='active'
    LEFT JOIN risk_rulesets r ON r.ruleset_id=j.ruleset_id AND r.state='active'
    WHERE j.product_id=p.product_id AND j.revision_no=p.current_revision_no AND j.context_version=p.context_version
      AND (j.model_id IS NULL OR (m.model_id IS NOT NULL AND r.ruleset_id IS NOT NULL))
      AND j.status IN ('queued','processing','failed')
    ORDER BY CASE WHEN j.status='processing' AND j.lease_expires_at>clock_timestamp() THEN 0 WHEN j.status IN ('queued','processing') THEN 1 ELSE 2 END,j.job_id DESC LIMIT 1
) current_work ON TRUE;

CREATE VIEW model_evaluation_metrics AS
SELECT e.*,true_positive::NUMERIC/NULLIF(true_positive+false_positive,0) AS precision,
       true_positive::NUMERIC/NULLIF(true_positive+false_negative,0) AS recall,
       2*true_positive::NUMERIC/NULLIF(2*true_positive+false_positive+false_negative,0) AS f1
FROM model_evaluations e;

-- Prevent default PUBLIC execution of privileged entry points and helper.
REVOKE ALL ON FUNCTION activate_risk_configuration(BIGINT,BIGINT),enqueue_product_scan(BIGINT),claim_risk_job(INTERVAL),
    locked_risk_claim(BIGINT,UUID),save_risk_snapshot(BIGINT,UUID,TIMESTAMPTZ,JSONB),heartbeat_risk_job(BIGINT,UUID,INTERVAL),
    fail_risk_job(BIGINT,UUID,VARCHAR,BOOLEAN),complete_risk_job(BIGINT,UUID,INTEGER,JSONB,JSONB),
    request_risk_rescan(BIGINT,UUID),create_daily_rescan(DATE,TEXT),run_rescan_batch(BIGINT,INTEGER) FROM PUBLIC;
COMMIT;
