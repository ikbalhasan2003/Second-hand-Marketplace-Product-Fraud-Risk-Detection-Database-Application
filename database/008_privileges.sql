-- Optional deployment hardening. Run as a trusted role with CREATEROLE after install.sql.
-- All application objects must already belong to a dedicated NON-LOGIN owner.
-- These group roles have no passwords; grant membership to separately configured LOGIN roles.
-- Trusted web code sets app.actor_id/action_reason from authenticated server context,
-- using SET LOCAL inside a transaction. The GUC is not end-user authentication.
BEGIN;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='secondhand_web') THEN CREATE ROLE secondhand_web NOLOGIN; END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='secondhand_worker') THEN CREATE ROLE secondhand_worker NOLOGIN; END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='secondhand_maintenance') THEN CREATE ROLE secondhand_maintenance NOLOGIN; END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='secondhand_training') THEN CREATE ROLE secondhand_training NOLOGIN; END IF;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO secondhand_web,secondhand_worker,secondhand_maintenance,secondhand_training;

-- Trigger-owned writes keep audit/order history append access away from the web role.
ALTER FUNCTION record_order_change() SECURITY DEFINER;
ALTER FUNCTION record_order_change() SET search_path=public,pg_temp;
ALTER FUNCTION audit_core_change() SECURITY DEFINER;
ALTER FUNCTION audit_core_change() SET search_path=public,pg_temp;
ALTER FUNCTION validate_appeal() SECURITY DEFINER;
ALTER FUNCTION validate_appeal() SET search_path=public,pg_temp;
ALTER FUNCTION queue_product_revision() SECURITY DEFINER;
ALTER FUNCTION queue_product_revision() SET search_path=public,pg_temp;

GRANT SELECT ON marketplace_settings,users,auth_group,users_groups,auth_permission,auth_group_permissions,
    users_user_permissions,django_content_type,django_session,categories,products,product_revisions,product_images,
    conversations,chat_messages,transactions,order_status_history,fraud_reports,report_attachments,
    moderation_reviews,admin_audit_logs,seller_appeals,notifications,feature_schemas,risk_models,risk_rulesets,
    risk_rules,risk_scan_jobs,risk_logs,risk_rescan_campaigns,risk_rescan_events,model_evaluations,
    current_listing_risk,risk_score_history,fraud_logs,admin_review_queue,seller_order_history,
    latest_effective_reviews,model_evaluation_metrics TO secondhand_web;
GRANT INSERT(email,password,full_name,location,private_contact) ON users TO secondhand_web;
GRANT UPDATE(password,full_name,location,private_contact,last_login,status,deactivated_at) ON users TO secondhand_web;
GRANT INSERT,UPDATE ON django_session,products,transactions,fraud_reports,seller_appeals TO secondhand_web;
GRANT DELETE ON django_session TO secondhand_web;
GRANT INSERT ON product_revisions,product_images,conversations,chat_messages,report_attachments,moderation_reviews TO secondhand_web;
GRANT INSERT,UPDATE ON risk_rulesets TO secondhand_web;
GRANT INSERT,UPDATE,DELETE ON risk_rules TO secondhand_web;
GRANT UPDATE(read_at) ON chat_messages,notifications TO secondhand_web;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO secondhand_web;
GRANT EXECUTE ON FUNCTION app_actor_id(),is_member(bigint,text),require_admin_actor(),require_action_reason(),
    place_order(bigint,bigint,integer,uuid,text),transition_order(bigint,text),
    effective_reviews_at(timestamptz),activate_risk_configuration(bigint,bigint),request_risk_rescan(bigint,uuid) TO secondhand_web;

CREATE OR REPLACE FUNCTION enable_marketplace_role(p_role text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE a bigint:=app_actor_id(); g integer;
BEGIN
    IF p_role NOT IN ('buyer','seller') OR a IS NULL OR NOT EXISTS
      (SELECT 1 FROM users WHERE user_id=a AND status='active' AND is_active) THEN
        RAISE EXCEPTION 'Active member and marketplace role required' USING ERRCODE='42501';
    END IF;
    SELECT id INTO g FROM auth_group WHERE name=p_role;
    IF g IS NULL THEN RAISE EXCEPTION 'Role groups must be provisioned first'; END IF;
    INSERT INTO users_groups(user_id,group_id) VALUES(a,g) ON CONFLICT DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION enable_marketplace_role(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION enable_marketplace_role(text) TO secondhand_web;

-- Worker reads the necessary feature facts, but cannot directly mutate jobs/results.
GRANT SELECT ON users,products,product_revisions,product_images,categories,moderation_reviews,
    risk_scan_jobs,risk_models,risk_rulesets,risk_rules,feature_schemas TO secondhand_worker;
GRANT EXECUTE ON FUNCTION effective_reviews_at(timestamptz),claim_risk_job(interval),
    save_risk_snapshot(bigint,uuid,timestamptz,jsonb),heartbeat_risk_job(bigint,uuid,interval),
    fail_risk_job(bigint,uuid,varchar,boolean),complete_risk_job(bigint,uuid,integer,jsonb,jsonb) TO secondhand_worker;
GRANT SELECT ON risk_rescan_campaigns,risk_rescan_events,products,transactions TO secondhand_maintenance;
GRANT EXECUTE ON FUNCTION create_daily_rescan(date,text),run_rescan_batch(bigint,integer),expire_unanswered_orders(integer)
    TO secondhand_maintenance;

-- Offline training consumes a frozen, approved export rather than live private data.
GRANT SELECT ON dataset_sources,dataset_versions,dataset_split_groups,dataset_records,feature_schemas
    TO secondhand_training;
COMMENT ON ROLE secondhand_training IS 'Trusted offline export consumer. Contains no private chat/evidence/contact grants.';
-- Reapply a reviewed grant migration when adding tables/functions. Never use a blanket
-- default EXECUTE or table DML grant: it would expose SECURITY DEFINER helpers.
COMMIT;
