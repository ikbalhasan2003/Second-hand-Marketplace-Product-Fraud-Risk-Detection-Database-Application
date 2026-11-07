CREATE TABLE account_appeals (
 appeal_id bigserial PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES users(user_id),
 reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 10 AND 5000),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','reviewing','approved','rejected')),
 reviewer_id bigint REFERENCES users(user_id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 reviewed_at timestamptz,
 decision_notes text NOT NULL DEFAULT '',
 CHECK ((status IN ('pending','reviewing') AND reviewed_at IS NULL) OR
        (status IN ('approved','rejected') AND reviewed_at IS NOT NULL AND reviewer_id IS NOT NULL AND length(btrim(decision_notes)) BETWEEN 1 AND 5000))
);
CREATE UNIQUE INDEX account_appeals_one_open ON account_appeals(user_id) WHERE status IN ('pending','reviewing');
CREATE TABLE account_appeal_evidence (
 evidence_id bigserial PRIMARY KEY,
 appeal_id bigint NOT NULL REFERENCES account_appeals(appeal_id),
 storage_key text NOT NULL UNIQUE,
 content_type text NOT NULL CHECK(content_type IN ('image/jpeg','image/png','image/webp')),
 byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 5242880),
 content_sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE FUNCTION validate_account_appeal() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE a bigint:=app_actor_id(); u users%ROWTYPE;
BEGIN
 SELECT * INTO u FROM users WHERE user_id=NEW.user_id FOR UPDATE;
 IF TG_OP='INSERT' THEN
  IF a IS DISTINCT FROM NEW.user_id OR u.status<>'blocked' OR NOT u.is_active OR NEW.status<>'pending' OR NEW.reviewer_id IS NOT NULL OR NEW.reviewed_at IS NOT NULL OR NEW.decision_notes<>'' THEN
   RAISE EXCEPTION 'Blocked account owner required' USING ERRCODE='42501';
  END IF;
  NEW.created_at:=clock_timestamp();
 ELSE
  a:=require_admin_actor();
  IF OLD.status NOT IN ('pending','reviewing') OR NEW.status NOT IN ('reviewing','approved','rejected') OR NEW.status=OLD.status OR
    (to_jsonb(NEW)-ARRAY['status','reviewer_id','reviewed_at','decision_notes']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['status','reviewer_id','reviewed_at','decision_notes']) THEN
   RAISE EXCEPTION 'Invalid appeal transition' USING ERRCODE='23514';
  END IF;
  NEW.reviewer_id:=a;
  NEW.reviewed_at:=CASE WHEN NEW.status IN ('approved','rejected') THEN clock_timestamp() END;
  IF NEW.status='approved' THEN
   IF u.status<>'blocked' THEN RAISE EXCEPTION 'Account is no longer blocked'; END IF;
   UPDATE users SET status='active' WHERE user_id=NEW.user_id;
  END IF;
  INSERT INTO admin_audit_logs(admin_id,action_type,user_id,reason,before_data,after_data)
   VALUES(a,'account_appeal_decision',NEW.user_id,require_action_reason(),
   jsonb_build_object('appeal_id',OLD.appeal_id,'status',OLD.status),
   jsonb_build_object('appeal_id',NEW.appeal_id,'status',NEW.status,'decision_notes',NEW.decision_notes));
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER account_appeal_validate BEFORE INSERT OR UPDATE ON account_appeals FOR EACH ROW EXECUTE FUNCTION validate_account_appeal();
CREATE TRIGGER account_appeal_no_delete BEFORE DELETE ON account_appeals FOR EACH ROW EXECUTE FUNCTION reject_history_change();
CREATE FUNCTION validate_account_appeal_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id bigint; state text;
BEGIN
 SELECT user_id,status INTO owner_id,state FROM account_appeals WHERE appeal_id=NEW.appeal_id FOR UPDATE;
 IF owner_id IS DISTINCT FROM app_actor_id() OR state<>'pending' OR
    (SELECT count(*) FROM account_appeal_evidence WHERE appeal_id=NEW.appeal_id)>=3 THEN
  RAISE EXCEPTION 'Only owner may attach up to three images to a pending appeal' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER account_appeal_evidence_validate BEFORE INSERT ON account_appeal_evidence FOR EACH ROW EXECUTE FUNCTION validate_account_appeal_evidence();
CREATE TRIGGER account_appeal_evidence_immutable BEFORE UPDATE OR DELETE ON account_appeal_evidence FOR EACH ROW EXECUTE FUNCTION reject_history_change();
REVOKE ALL ON FUNCTION validate_account_appeal() FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='secondhand_web') THEN
  GRANT SELECT,INSERT,UPDATE ON account_appeals TO secondhand_web;
  GRANT SELECT,INSERT ON account_appeal_evidence TO secondhand_web;
  GRANT USAGE,SELECT ON SEQUENCE account_appeals_appeal_id_seq,account_appeal_evidence_evidence_id_seq TO secondhand_web;
 END IF;
END $$;
