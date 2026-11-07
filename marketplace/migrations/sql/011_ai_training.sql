CREATE TABLE ai_training_jobs (
 job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 dataset_id bigint NOT NULL REFERENCES dataset_versions,
 requested_by bigint NOT NULL REFERENCES users(user_id),
 source_audit_id bigint NOT NULL REFERENCES admin_audit_logs,
 configuration jsonb NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 retry_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 model_id bigint REFERENCES risk_models,
 error_code text,
 error_message text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(dataset_id)
);
CREATE FUNCTION app_enqueue_training(p_dataset bigint) RETURNS bigint LANGUAGE plpgsql
SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE d dataset_versions; a bigint; j bigint; actor bigint;
BEGIN
 actor:=require_admin_actor();
 PERFORM require_action_reason();
 SELECT * INTO d FROM dataset_versions WHERE dataset_id=p_dataset AND state='frozen' FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Choose a frozen dataset'; END IF;
 SELECT job_id INTO j FROM ai_training_jobs WHERE dataset_id=p_dataset;
 IF FOUND THEN RETURN j; END IF;
 INSERT INTO admin_audit_logs(admin_id,action_type,dataset_id,reason,after_data)
 VALUES(actor,'ai_training_requested',p_dataset,current_setting('app.action_reason',true),
 jsonb_build_object('policy','manual activation after evaluation','dataset_sha256',d.dataset_sha256)) RETURNING audit_id INTO a;
 INSERT INTO ai_training_jobs(dataset_id,requested_by,source_audit_id,configuration)
 VALUES(p_dataset,actor,a,jsonb_build_object('dataset',to_jsonb(d),'pipeline','marketplace-v1-rf-200-v1',
 'activation','manual','minimum_partition_samples',10,'minimum_precision',0.5,'minimum_recall',0.5))
 ON CONFLICT(dataset_id) DO UPDATE SET dataset_id=excluded.dataset_id RETURNING job_id INTO j;
 RETURN j;
END $$;
CREATE FUNCTION enqueue_frozen_dataset_training() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 IF NEW.state='frozen' AND OLD.state IS DISTINCT FROM NEW.state THEN
  PERFORM app_enqueue_training(NEW.dataset_id);
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER frozen_dataset_training AFTER UPDATE OF state ON dataset_versions
FOR EACH ROW EXECUTE FUNCTION enqueue_frozen_dataset_training();
REVOKE ALL ON ai_training_jobs FROM PUBLIC;
REVOKE ALL ON FUNCTION app_enqueue_training(bigint),enqueue_frozen_dataset_training() FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='secondhand_web') THEN
  GRANT SELECT ON ai_training_jobs TO secondhand_web;
  GRANT EXECUTE ON FUNCTION app_enqueue_training(bigint) TO secondhand_web;
 END IF;
END $$;
