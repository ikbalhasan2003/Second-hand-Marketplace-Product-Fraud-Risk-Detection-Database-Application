-- Additive reconciliation; never rewrite historical purchase assessments or labels.
CREATE INDEX account_appeals_queue_idx ON account_appeals(status,created_at,appeal_id);
CREATE INDEX account_appeals_reviewer_idx ON account_appeals(reviewer_id);
CREATE INDEX account_appeal_evidence_appeal_idx ON account_appeal_evidence(appeal_id);
CREATE INDEX ai_training_jobs_queue_idx ON ai_training_jobs(retry_at,job_id)
 WHERE status IN ('queued','failed');
CREATE INDEX ai_training_jobs_requester_idx ON ai_training_jobs(requested_by);
CREATE INDEX ai_training_jobs_audit_idx ON ai_training_jobs(source_audit_id);
CREATE INDEX ai_training_jobs_model_idx ON ai_training_jobs(model_id);

CREATE FUNCTION guard_training_job_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'Training job provenance cannot be deleted' USING ERRCODE='23514';
 END IF;
 IF (to_jsonb(NEW)-ARRAY['status','attempts','retry_at','model_id','error_code','error_message','updated_at'])
    IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['status','attempts','retry_at','model_id','error_code','error_message','updated_at']) THEN
  RAISE EXCEPTION 'Training job provenance is immutable' USING ERRCODE='23514';
 END IF;
 IF OLD.status='succeeded' AND NEW IS DISTINCT FROM OLD THEN
  RAISE EXCEPTION 'Successful training receipt is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER training_job_history BEFORE UPDATE OR DELETE ON ai_training_jobs
 FOR EACH ROW EXECUTE FUNCTION guard_training_job_history();
REVOKE ALL ON FUNCTION guard_training_job_history(),validate_account_appeal_evidence(),
 audit_marketplace_policy() FROM PUBLIC;
