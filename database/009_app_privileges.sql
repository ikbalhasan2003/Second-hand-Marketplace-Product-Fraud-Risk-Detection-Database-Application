-- Apply after Django migrations and database/008_privileges.sql as controlled owner.
BEGIN;
GRANT SELECT,INSERT,UPDATE,DELETE ON app_rate_limits,app_listing_drafts TO secondhand_web;
GRANT SELECT ON dataset_versions,dataset_records,dataset_sources,dataset_split_groups TO secondhand_web;
GRANT EXECUTE ON FUNCTION app_audit_ruleset_draft(bigint),app_audit_dataset_download(bigint,text),
    app_register_reviewed_export(text,timestamptz,bigint,bigint,text,text,jsonb) TO secondhand_web;
GRANT EXECUTE ON FUNCTION listing_publication_allowed(bigint) TO secondhand_web;

GRANT UPDATE(unanswered_order_timeout) ON marketplace_settings TO secondhand_web;

GRANT SELECT,INSERT,UPDATE ON account_appeals TO secondhand_web;
GRANT SELECT,INSERT ON account_appeal_evidence TO secondhand_web;
GRANT USAGE,SELECT ON SEQUENCE account_appeals_appeal_id_seq,account_appeal_evidence_evidence_id_seq TO secondhand_web;

GRANT SELECT ON ai_training_jobs TO secondhand_web;
GRANT EXECUTE ON FUNCTION app_enqueue_training(bigint) TO secondhand_web;

-- Dedicated trusted trainer: register candidates, never activate configurations.
GRANT SELECT ON ai_training_jobs,risk_models,model_evaluations,risk_rulesets,
    users_groups,auth_group TO secondhand_training;
GRANT SELECT(user_id,status,is_active) ON users TO secondhand_training;
GRANT UPDATE(status,attempts,retry_at,model_id,error_code,error_message,updated_at)
    ON ai_training_jobs TO secondhand_training;
GRANT INSERT ON risk_models,model_evaluations,admin_audit_logs TO secondhand_training;
GRANT USAGE,SELECT ON SEQUENCE risk_models_model_id_seq,
    model_evaluations_evaluation_id_seq,admin_audit_logs_audit_id_seq TO secondhand_training;
GRANT EXECUTE ON FUNCTION app_actor_id(),is_member(bigint,text),require_admin_actor(),
    require_action_reason() TO secondhand_training;
-- History is readable for controlled administration, never writable by runtime roles.
GRANT SELECT ON administrator_transitions TO secondhand_web;
REVOKE ALL ON FUNCTION validate_account_appeal_evidence(),guard_training_job_history(),
    audit_marketplace_policy() FROM PUBLIC;
COMMIT;
