-- Apply after Django migrations and database/008_privileges.sql as controlled owner.
BEGIN;
GRANT SELECT,INSERT,UPDATE,DELETE ON app_rate_limits,app_listing_drafts TO secondhand_web;
GRANT SELECT ON dataset_versions,dataset_records,dataset_sources,dataset_split_groups TO secondhand_web;
GRANT EXECUTE ON FUNCTION app_audit_ruleset_draft(bigint),app_audit_dataset_download(bigint,text),
    app_register_reviewed_export(text,timestamptz,bigint,bigint,text,text,jsonb) TO secondhand_web;
COMMIT;
