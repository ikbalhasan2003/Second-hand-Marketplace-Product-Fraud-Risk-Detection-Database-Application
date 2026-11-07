-- Retain the target invariant, extending it explicitly for singleton policy receipts.
ALTER TABLE admin_audit_logs DROP CONSTRAINT admin_audit_logs_check;
ALTER TABLE admin_audit_logs ADD CONSTRAINT admin_audit_logs_check CHECK (
    num_nonnulls(user_id,product_id,report_id,review_id,transaction_id,model_id,ruleset_id,dataset_id)>=1
    OR (action_type='marketplace_policy_change' AND after_data @> '{"target":"marketplace_settings","singleton":true}'::jsonb)
);
CREATE OR REPLACE FUNCTION audit_core_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a bigint; target_user bigint; target_product bigint; target_report bigint; target_review bigint; action text; before_record jsonb := '{}'; after_record jsonb := '{}';
BEGIN
    IF TG_TABLE_NAME='users' THEN
        IF NEW.status=OLD.status THEN RETURN NULL; END IF;
        target_user:=NEW.user_id; action:='account_status_change';
        before_record:=jsonb_build_object('status',OLD.status); after_record:=jsonb_build_object('status',NEW.status);
    ELSIF TG_TABLE_NAME='products' THEN
        IF NEW.visibility=OLD.visibility OR (NEW.visibility<>'removed_by_admin' AND OLD.visibility<>'removed_by_admin') THEN RETURN NULL; END IF;
        target_product:=NEW.product_id; action:='listing_visibility_change';
        before_record:=jsonb_build_object('visibility',OLD.visibility); after_record:=jsonb_build_object('visibility',NEW.visibility);
    ELSIF TG_TABLE_NAME='fraud_reports' THEN
        target_report:=NEW.report_id; action:='report_update';
        before_record:=jsonb_build_object('status',OLD.status,'assigned_admin_id',OLD.assigned_admin_id,'public_outcome',OLD.public_outcome,'resolved_at',OLD.resolved_at);
        after_record:=jsonb_build_object('status',NEW.status,'assigned_admin_id',NEW.assigned_admin_id,'public_outcome',NEW.public_outcome,'resolved_at',NEW.resolved_at);
    ELSE
        target_review:=NEW.review_id; target_product:=NEW.product_id; action:='moderation_decision';
        after_record:=jsonb_build_object('verdict',NEW.verdict,'supersedes_review_id',NEW.supersedes_review_id);
    END IF;
    a:=require_admin_actor();
    INSERT INTO admin_audit_logs(admin_id,action_type,user_id,product_id,report_id,review_id,reason,before_data,after_data)
      VALUES(a,action,target_user,target_product,target_report,target_review,require_action_reason(),before_record,after_record);
    RETURN NULL;
END $$;

CREATE FUNCTION audit_marketplace_policy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actor bigint;
BEGIN
    actor := require_admin_actor();
    IF (to_jsonb(NEW)-'unanswered_order_timeout') IS DISTINCT FROM (to_jsonb(OLD)-'unanswered_order_timeout') THEN
        RAISE EXCEPTION 'Only unanswered order timeout is editable through marketplace policy';
    END IF;
    IF NEW.unanswered_order_timeout < interval '1 hour' OR NEW.unanswered_order_timeout > interval '8760 hours' THEN
        RAISE EXCEPTION 'Timeout must be between 1 and 8760 hours';
    END IF;
    IF NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
    INSERT INTO admin_audit_logs(admin_id,action_type,reason,before_data,after_data)
    VALUES(actor,'marketplace_policy_change',require_action_reason(),
        jsonb_build_object('target','marketplace_settings','singleton',true,'unanswered_order_timeout',OLD.unanswered_order_timeout),
        jsonb_build_object('target','marketplace_settings','singleton',true,'unanswered_order_timeout',NEW.unanswered_order_timeout));
    RETURN NEW;
END $$;
CREATE TRIGGER marketplace_policy_audit BEFORE UPDATE ON marketplace_settings
FOR EACH ROW EXECUTE FUNCTION audit_marketplace_policy();
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='secondhand_web') THEN
        GRANT UPDATE(unanswered_order_timeout) ON marketplace_settings TO secondhand_web;
    END IF;
END $$;
