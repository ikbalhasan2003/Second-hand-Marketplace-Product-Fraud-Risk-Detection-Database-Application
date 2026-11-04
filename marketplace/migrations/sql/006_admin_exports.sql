-- Controlled Admin helpers. Browsers never receive database credentials.
CREATE FUNCTION app_audit_ruleset_draft(p_ruleset bigint) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE a bigint; result bigint;
BEGIN
    a:=require_admin_actor(); PERFORM require_action_reason();
    IF NOT EXISTS(SELECT 1 FROM risk_rulesets WHERE ruleset_id=p_ruleset AND state='draft' AND created_by=a) THEN
        RAISE EXCEPTION 'Administrator-owned draft required';
    END IF;
    INSERT INTO admin_audit_logs(admin_id,action_type,ruleset_id,reason,after_data)
    VALUES(a,'ruleset_draft_created',p_ruleset,require_action_reason(),jsonb_build_object('state','draft')) RETURNING audit_id INTO result;
    RETURN result;
END $$;

CREATE FUNCTION app_audit_dataset_download(p_dataset bigint,p_sha text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE result bigint;
BEGIN
    PERFORM require_admin_actor(); PERFORM require_action_reason();
    IF NOT EXISTS(SELECT 1 FROM dataset_versions WHERE dataset_id=p_dataset AND state='frozen' AND dataset_sha256=p_sha) THEN
        RAISE EXCEPTION 'Download must match a frozen dataset checksum';
    END IF;
    INSERT INTO admin_audit_logs(admin_id,action_type,dataset_id,reason,after_data)
    VALUES(require_admin_actor(),'dataset_download',p_dataset,require_action_reason(),jsonb_build_object('dataset_sha256',p_sha)) RETURNING audit_id INTO result;
    RETURN result;
END $$;

CREATE FUNCTION app_register_reviewed_export(p_version text,p_cutoff timestamptz,p_seed bigint,p_schema bigint,p_manifest text,p_sha text,p_rows jsonb) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE d bigint; source bigint; item jsonb; j risk_scan_jobs%ROWTYPE; r moderation_reviews%ROWTYPE;
    seller bigint; fingerprint text; seller_key text; record_key text; group_id bigint;
BEGIN
    PERFORM require_admin_actor(); PERFORM require_action_reason();
    IF p_cutoff IS NULL OR p_rows IS NULL OR p_manifest IS NULL OR p_sha IS NULL OR p_cutoff>clock_timestamp() OR p_manifest !~ '^exports/[0-9a-f-]+/manifest.json$'
       OR p_sha !~ '^[0-9a-f]{64}$' OR jsonb_typeof(p_rows)<>'array' OR jsonb_array_length(p_rows) NOT BETWEEN 1 AND 10000 THEN
        RAISE EXCEPTION 'Invalid reviewed export scope or manifest';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM feature_schemas WHERE feature_schema_id=p_schema AND version='marketplace-v1') THEN
        RAISE EXCEPTION 'Approved marketplace-v1 schema required';
    END IF;
    INSERT INTO dataset_versions(version,feature_schema_id,seed,export_cutoff,split_strategy,created_by)
    VALUES(p_version,p_schema,p_seed,p_cutoff,'Connected seller and normalized-text duplicate components; deterministic 70/15/15 grouped allocation',require_admin_actor()) RETURNING dataset_id INTO d;
    INSERT INTO dataset_sources(source_key,source_type,attribution,license_access_notes)
    VALUES('project-reviewed-v1','project_review','Project evidence-backed canonical moderation decisions','Administrator-approved course research; no private contacts, chats or attachments')
    ON CONFLICT(source_key) DO NOTHING;
    SELECT source_id INTO source FROM dataset_sources WHERE source_key='project-reviewed-v1';
    FOR item IN SELECT value FROM jsonb_array_elements(p_rows) LOOP
        SELECT * INTO r FROM moderation_reviews WHERE review_id=(item->>'review_id')::bigint;
        IF NOT FOUND OR r.reviewed_at>p_cutoff OR r.verdict NOT IN ('fraud','legitimate') OR length(btrim(r.evidence_summary))=0 OR EXISTS
           (SELECT 1 FROM moderation_reviews newer WHERE newer.product_id=r.product_id AND newer.revision_no=r.revision_no AND newer.reviewed_at<=p_cutoff AND (newer.reviewed_at,newer.review_id)>(r.reviewed_at,r.review_id)) THEN
            RAISE EXCEPTION 'Export label is no longer canonical and eligible';
        END IF;
        SELECT * INTO j FROM risk_scan_jobs WHERE job_id=(item->>'job_id')::bigint;
        IF NOT FOUND OR (j.product_id,j.revision_no) IS DISTINCT FROM (r.product_id,r.revision_no)
           OR j.feature_schema_id IS DISTINCT FROM p_schema OR j.feature_as_of>r.reviewed_at OR j.feature_as_of>p_cutoff
           OR j.feature_snapshot IS NULL OR j.feature_snapshot->>'schema_version' IS DISTINCT FROM 'marketplace-v1'
           OR j.feature_snapshot->'feature_evidence'->>'point_in_time_snapshot' IS DISTINCT FROM 'true' THEN
            RAISE EXCEPTION 'Export requires compatible frozen point-in-time features';
        END IF;
        SELECT p.seller_id,v.text_fingerprint INTO seller,fingerprint FROM products p JOIN product_revisions v USING(product_id)
        WHERE v.product_id=r.product_id AND v.revision_no=r.revision_no;
        seller_key:=encode(sha256(convert_to('seller:'||seller,'UTF8')),'hex');
        record_key:=encode(sha256(convert_to('review:'||r.review_id,'UTF8')),'hex');
        INSERT INTO dataset_split_groups(dataset_id,group_key,partition) VALUES(d,seller_key,item->>'partition')
        ON CONFLICT(dataset_id,group_key) DO NOTHING;
        SELECT split_group_id INTO group_id FROM dataset_split_groups WHERE dataset_id=d AND group_key=seller_key;
        IF NOT EXISTS(SELECT 1 FROM dataset_split_groups WHERE dataset_id=d AND split_group_id=group_id AND partition=item->>'partition') THEN
            RAISE EXCEPTION 'Seller grouping crosses partitions';
        END IF;
        INSERT INTO dataset_records(dataset_id,record_key,source_id,split_group_id,product_id,revision_no,review_id,seller_group_key,duplicate_group_key,
            feature_as_of,feature_values,label,label_source,label_decided_at,is_synthetic)
        VALUES(d,record_key,source,group_id,r.product_id,r.revision_no,r.review_id,seller_key,fingerprint,j.feature_as_of,
            jsonb_build_object('features',j.feature_snapshot->'features','feature_evidence',j.feature_snapshot->'feature_evidence','category',item->>'category'),
            r.verdict,'moderation_review',r.reviewed_at,false);
    END LOOP;
    UPDATE dataset_versions SET state='frozen',manifest_key=p_manifest,dataset_sha256=p_sha,frozen_at=clock_timestamp() WHERE dataset_id=d;
    RETURN d;
END $$;
REVOKE ALL ON FUNCTION app_audit_ruleset_draft(bigint),app_audit_dataset_download(bigint,text),app_register_reviewed_export(text,timestamptz,bigint,bigint,text,text,jsonb) FROM PUBLIC;

