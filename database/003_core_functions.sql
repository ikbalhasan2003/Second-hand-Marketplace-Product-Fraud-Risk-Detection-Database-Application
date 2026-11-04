BEGIN;

CREATE FUNCTION app_actor_id() RETURNS bigint LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('app.actor_id', true),'')::bigint
$$;
CREATE FUNCTION is_member(p_user bigint,p_role text) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM users_groups ug JOIN auth_group g ON g.id=ug.group_id
                   WHERE ug.user_id=p_user AND g.name=p_role)
$$;
CREATE FUNCTION require_admin_actor() RETURNS bigint LANGUAGE plpgsql STABLE AS $$
DECLARE a bigint := app_actor_id();
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE user_id=a AND status='active' AND is_active)
       OR NOT is_member(a,'administrator') THEN
        RAISE EXCEPTION 'Active administrator actor required' USING ERRCODE='42501';
    END IF;
    RETURN a;
END $$;
CREATE FUNCTION require_action_reason() RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE r text := nullif(btrim(current_setting('app.action_reason',true)),'');
BEGIN
    IF r IS NULL THEN RAISE EXCEPTION 'Action reason required' USING ERRCODE='23514'; END IF;
    RETURN r;
END $$;
CREATE FUNCTION reject_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is retained immutable history',TG_TABLE_NAME USING ERRCODE='23514'; END $$;

CREATE FUNCTION validate_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE role_name text;
BEGIN
    PERFORM 1 FROM users WHERE user_id=NEW.user_id FOR UPDATE;
    SELECT name INTO role_name FROM auth_group WHERE id=NEW.group_id;
    IF (role_name='administrator' AND (is_member(NEW.user_id,'buyer') OR is_member(NEW.user_id,'seller')))
       OR (role_name IN ('buyer','seller') AND is_member(NEW.user_id,'administrator')) THEN
        RAISE EXCEPTION 'Administrator and marketplace memberships are disjoint' USING ERRCODE='23514';
    END IF;
    IF role_name IN ('buyer','seller') AND NOT EXISTS
       (SELECT 1 FROM users WHERE user_id=NEW.user_id AND status='active' AND is_active) THEN
        RAISE EXCEPTION 'Inactive member cannot gain marketplace access' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER membership_guard BEFORE INSERT OR UPDATE ON users_groups FOR EACH ROW EXECUTE FUNCTION validate_membership();

CREATE FUNCTION guard_marketplace_settings() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Marketplace configuration is required'; END IF;
    IF NEW.currency<>OLD.currency AND EXISTS(SELECT 1 FROM product_revisions) THEN
        RAISE EXCEPTION 'Currency cannot change after revisions exist';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=NEW.refresh_timezone) THEN
        RAISE EXCEPTION 'Unknown refresh timezone';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER marketplace_settings_guard BEFORE UPDATE OR DELETE ON marketplace_settings FOR EACH ROW EXECUTE FUNCTION guard_marketplace_settings();

CREATE FUNCTION validate_product() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a bigint := app_actor_id();
BEGIN
    IF TG_OP='INSERT' THEN
        IF a IS DISTINCT FROM NEW.seller_id OR NOT is_member(NEW.seller_id,'seller') OR NOT EXISTS
          (SELECT 1 FROM users WHERE user_id=NEW.seller_id AND status='active' AND is_active) THEN
            RAISE EXCEPTION 'Active seller membership required' USING ERRCODE='23514';
        END IF;
    ELSE
        IF NEW.seller_id <> OLD.seller_id OR NEW.created_at <> OLD.created_at OR
            NEW.first_published_at IS DISTINCT FROM OLD.first_published_at THEN
            RAISE EXCEPTION 'Seller and original publication facts are immutable' USING ERRCODE='23514';
        END IF;
        IF NEW.current_revision_no IS DISTINCT FROM OLD.current_revision_no THEN
            IF a IS DISTINCT FROM NEW.seller_id OR NOT is_member(NEW.seller_id,'seller') OR NOT EXISTS
              (SELECT 1 FROM users WHERE user_id=NEW.seller_id AND status='active' AND is_active) THEN
                RAISE EXCEPTION 'Active owner required to advance content' USING ERRCODE='42501';
            END IF;
            IF EXISTS (SELECT 1 FROM transactions WHERE product_id=OLD.product_id AND status<>'cancelled') THEN
                RAISE EXCEPTION 'Purchased/reserved listing cannot be materially edited' USING ERRCODE='23514';
            END IF;
            IF NEW.current_revision_no IS NULL OR NEW.current_revision_no <= coalesce(OLD.current_revision_no,0) THEN
                RAISE EXCEPTION 'Current revision must advance' USING ERRCODE='23514';
            END IF;
            NEW.context_version := OLD.context_version+1;
        ELSIF NEW.context_version < OLD.context_version THEN
            RAISE EXCEPTION 'Context version cannot decrease' USING ERRCODE='23514';
        END IF;
        IF NEW.visibility IS DISTINCT FROM OLD.visibility THEN
            IF NEW.visibility='removed_by_admin' OR OLD.visibility='removed_by_admin' THEN
                PERFORM require_admin_actor(); PERFORM require_action_reason();
            ELSIF a IS DISTINCT FROM NEW.seller_id THEN
                RAISE EXCEPTION 'Seller actor required' USING ERRCODE='42501';
            END IF;
            IF NEW.visibility='removed_by_seller' AND EXISTS
              (SELECT 1 FROM transactions WHERE product_id=NEW.product_id AND status IN ('placed','accepted','shipped','disputed')) THEN
                RAISE EXCEPTION 'Resolve active order before seller withdrawal' USING ERRCODE='23514';
            END IF;
        END IF;
    END IF;
    IF NEW.availability='available' AND (TG_OP='INSERT' OR OLD.availability='draft') THEN
        IF a IS DISTINCT FROM NEW.seller_id OR NOT is_member(NEW.seller_id,'seller') OR NOT EXISTS
          (SELECT 1 FROM users WHERE user_id=NEW.seller_id AND status='active' AND is_active) THEN
            RAISE EXCEPTION 'Active seller actor required to publish' USING ERRCODE='42501';
        END IF;
        NEW.first_published_at := coalesce(NEW.first_published_at,clock_timestamp());
        IF TG_OP='UPDATE' THEN NEW.context_version := greatest(NEW.context_version,OLD.context_version+1); END IF;
    END IF;
    NEW.updated_at := clock_timestamp(); RETURN NEW;
END $$;
CREATE TRIGGER product_guard BEFORE INSERT OR UPDATE ON products FOR EACH ROW EXECUTE FUNCTION validate_product();

CREATE FUNCTION validate_revision_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p products%ROWTYPE;
BEGIN
    SELECT * INTO p FROM products WHERE product_id=NEW.product_id FOR UPDATE;
    IF app_actor_id() IS DISTINCT FROM p.seller_id OR NOT is_member(p.seller_id,'seller') OR NOT EXISTS
       (SELECT 1 FROM users WHERE user_id=p.seller_id AND status='active' AND is_active) THEN
        RAISE EXCEPTION 'Active owner required to create revision' USING ERRCODE='42501';
    END IF;
    IF EXISTS (SELECT 1 FROM transactions WHERE product_id=NEW.product_id AND status<>'cancelled') THEN
        RAISE EXCEPTION 'Purchased/reserved listing cannot gain revisions' USING ERRCODE='23514';
    END IF;
    IF NEW.revision_no <> (SELECT coalesce(max(revision_no),0)+1 FROM product_revisions WHERE product_id=NEW.product_id) THEN
        RAISE EXCEPTION 'Revision number must be next in sequence' USING ERRCODE='23514';
    END IF;
    IF NEW.currency IS DISTINCT FROM (SELECT currency FROM marketplace_settings WHERE singleton) THEN
        RAISE EXCEPTION 'Revision currency must match marketplace configuration' USING ERRCODE='23514';
    END IF;
    NEW.created_at := clock_timestamp(); NEW.created_xid := pg_current_xact_id(); RETURN NEW;
END $$;
CREATE TRIGGER revision_insert_guard BEFORE INSERT ON product_revisions FOR EACH ROW EXECUTE FUNCTION validate_revision_insert();
CREATE TRIGGER revision_immutable BEFORE UPDATE OR DELETE ON product_revisions FOR EACH ROW EXECUTE FUNCTION reject_history_change();
CREATE FUNCTION validate_image_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM product_revisions r JOIN products p USING(product_id)
       WHERE r.product_id=NEW.product_id AND r.revision_no=NEW.revision_no
       AND r.created_xid=pg_current_xact_id() AND p.seller_id=app_actor_id()) THEN
        RAISE EXCEPTION 'Attach images in revision creation transaction only' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER image_insert_guard BEFORE INSERT ON product_images FOR EACH ROW EXECUTE FUNCTION validate_image_insert();
CREATE TRIGGER image_immutable BEFORE UPDATE OR DELETE ON product_images FOR EACH ROW EXECUTE FUNCTION reject_history_change();

CREATE FUNCTION validate_conversation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s bigint;
BEGIN
    SELECT seller_id INTO s FROM products WHERE product_id=NEW.product_id;
    IF s=NEW.buyer_id OR app_actor_id() IS DISTINCT FROM NEW.buyer_id OR NOT is_member(NEW.buyer_id,'buyer')
       OR NOT EXISTS (SELECT 1 FROM users WHERE user_id=NEW.buyer_id AND status='active' AND is_active) THEN
        RAISE EXCEPTION 'Active buyer and non-self conversation required' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER conversation_guard BEFORE INSERT ON conversations FOR EACH ROW EXECUTE FUNCTION validate_conversation();
CREATE TRIGGER conversation_immutable BEFORE UPDATE OR DELETE ON conversations FOR EACH ROW EXECUTE FUNCTION reject_history_change();
CREATE FUNCTION validate_message() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b bigint; s bigint; a bigint := app_actor_id();
BEGIN
    SELECT c.buyer_id,p.seller_id INTO b,s FROM conversations c JOIN products p USING(product_id)
        WHERE c.conversation_id=NEW.conversation_id;
    IF TG_OP='INSERT' THEN
        IF a IS DISTINCT FROM NEW.sender_id OR NEW.sender_id NOT IN (b,s) OR NOT EXISTS
            (SELECT 1 FROM users WHERE user_id=a AND status='active' AND is_active) OR NEW.read_at IS NOT NULL THEN
            RAISE EXCEPTION 'Active conversation participant required' USING ERRCODE='42501';
        END IF;
        NEW.sent_at := clock_timestamp();
    ELSE
        IF (to_jsonb(NEW)-'read_at') IS DISTINCT FROM (to_jsonb(OLD)-'read_at')
          OR OLD.read_at IS NOT NULL OR NEW.read_at IS NULL OR a IS NULL OR a NOT IN (b,s) OR a=OLD.sender_id THEN
            RAISE EXCEPTION 'Only recipient may record initial read receipt' USING ERRCODE='42501';
        END IF;
        NEW.read_at := clock_timestamp();
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER message_guard BEFORE INSERT OR UPDATE ON chat_messages FOR EACH ROW EXECUTE FUNCTION validate_message();
CREATE TRIGGER message_retained BEFORE DELETE ON chat_messages FOR EACH ROW EXECUTE FUNCTION reject_history_change();

CREATE FUNCTION validate_order() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p products%ROWTYPE; a bigint := app_actor_id(); permitted boolean := false;
BEGIN
    SELECT * INTO p FROM products WHERE product_id=NEW.product_id FOR UPDATE;
    IF TG_OP='INSERT' THEN
        IF a IS DISTINCT FROM NEW.buyer_id OR NOT is_member(NEW.buyer_id,'buyer') OR NEW.buyer_id=p.seller_id
          OR NEW.status<>'placed' OR p.availability<>'available' OR p.visibility<>'visible'
          OR NEW.revision_no IS DISTINCT FROM p.current_revision_no
          OR (SELECT count(*) FROM users WHERE user_id IN (NEW.buyer_id,p.seller_id) AND status='active' AND is_active)<>2 THEN
            RAISE EXCEPTION 'Listing unavailable or buyer invalid' USING ERRCODE='23514';
        END IF;
        NEW.created_at := clock_timestamp();
    ELSE
        IF (to_jsonb(NEW)-ARRAY['status','updated_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','updated_at']) THEN
            RAISE EXCEPTION 'Order purchase facts are immutable' USING ERRCODE='23514';
        END IF;
        IF NEW.status=OLD.status THEN RETURN OLD; END IF;
        IF OLD.status='placed' THEN
            permitted := (NEW.status='accepted' AND a=p.seller_id)
              OR (NEW.status IN ('cancelled','disputed') AND a IN (OLD.buyer_id,p.seller_id));
            IF a IS NULL AND current_setting('app.system_action',true)='order_expiry'
              AND NEW.status='cancelled' AND OLD.created_at<=clock_timestamp()-(SELECT unanswered_order_timeout FROM marketplace_settings WHERE singleton) THEN permitted:=true; END IF;
        ELSIF OLD.status='accepted' THEN
            permitted := (NEW.status='shipped' AND a=p.seller_id) OR (NEW.status='completed' AND a=OLD.buyer_id)
              OR (NEW.status IN ('cancelled','disputed') AND a IN (OLD.buyer_id,p.seller_id));
        ELSIF OLD.status='shipped' THEN
            permitted := (NEW.status='completed' AND a=OLD.buyer_id)
              OR (NEW.status='disputed' AND a IN (OLD.buyer_id,p.seller_id));
        ELSIF OLD.status='disputed' AND NEW.status IN ('completed','cancelled') THEN
            PERFORM require_admin_actor(); PERFORM require_action_reason(); permitted:=true;
        END IF;
        IF NOT coalesce(permitted,false) THEN RAISE EXCEPTION 'Invalid order transition/actor' USING ERRCODE='23514'; END IF;
    END IF;
    NEW.updated_at := clock_timestamp(); RETURN NEW;
END $$;
CREATE TRIGGER order_guard BEFORE INSERT OR UPDATE ON transactions FOR EACH ROW EXECUTE FUNCTION validate_order();
CREATE TRIGGER order_retained BEFORE DELETE ON transactions FOR EACH ROW EXECUTE FUNCTION reject_history_change();
CREATE FUNCTION record_order_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a bigint := app_actor_id(); r text := coalesce(nullif(current_setting('app.action_reason',true),''),'Order workflow');
BEGIN
    IF TG_OP='UPDATE' AND OLD.status=NEW.status THEN RETURN NULL; END IF;
    INSERT INTO order_status_history(transaction_id,from_status,to_status,actor_id,system_actor,reason)
      VALUES(NEW.transaction_id,CASE WHEN TG_OP='UPDATE' THEN OLD.status END,NEW.status,a,
        CASE WHEN a IS NULL THEN 'order_expiry' END,r);
    UPDATE products SET availability=CASE NEW.status WHEN 'cancelled' THEN 'available'
      WHEN 'completed' THEN 'sold' ELSE 'reserved' END WHERE product_id=NEW.product_id;
    IF TG_OP='UPDATE' AND OLD.status='disputed' THEN
        INSERT INTO admin_audit_logs(admin_id,action_type,transaction_id,product_id,reason,before_data,after_data)
        VALUES(require_admin_actor(),'order_dispute_resolution',NEW.transaction_id,NEW.product_id,require_action_reason(),
          jsonb_build_object('status',OLD.status),jsonb_build_object('status',NEW.status));
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER order_record AFTER INSERT OR UPDATE ON transactions FOR EACH ROW EXECUTE FUNCTION record_order_change();
CREATE TRIGGER order_history_immutable BEFORE UPDATE OR DELETE ON order_status_history FOR EACH ROW EXECUTE FUNCTION reject_history_change();

CREATE FUNCTION check_product_order_state() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE pid bigint; av text; os text;
BEGIN
    pid := NEW.product_id;
    SELECT availability INTO av FROM products WHERE product_id=pid;
    SELECT status INTO os FROM transactions WHERE product_id=pid AND status<>'cancelled';
    IF (os='completed' AND av<>'sold') OR (os IN ('placed','accepted','shipped','disputed') AND av<>'reserved')
       OR (os IS NULL AND av IN ('reserved','sold')) THEN
        RAISE EXCEPTION 'Product availability disagrees with order state' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER product_order_consistency AFTER INSERT OR UPDATE ON products
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_product_order_state();
CREATE CONSTRAINT TRIGGER order_product_consistency AFTER INSERT OR UPDATE ON transactions
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_product_order_state();

CREATE FUNCTION place_order(p_buyer bigint,p_product bigint,p_revision integer,p_key uuid,p_fingerprint text)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE existing transactions%ROWTYPE; result_id bigint; seller bigint;
BEGIN
    IF app_actor_id() IS DISTINCT FROM p_buyer THEN RAISE EXCEPTION 'Buyer actor mismatch' USING ERRCODE='42501'; END IF;
    -- Serialize replays first, then product. Web services lock affected users before calling.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_buyer::text||':'||p_key::text,0));
    SELECT * INTO existing FROM transactions WHERE buyer_id=p_buyer AND request_key=p_key;
    IF FOUND THEN
        IF existing.product_id<>p_product OR existing.revision_no<>p_revision OR existing.request_fingerprint<>p_fingerprint THEN
            RAISE EXCEPTION 'Idempotency key reused for different request' USING ERRCODE='23514';
        END IF;
        RETURN existing.transaction_id;
    END IF;
    SELECT seller_id INTO seller FROM products WHERE product_id=p_product;
    PERFORM 1 FROM users WHERE user_id IN (p_buyer,seller) ORDER BY user_id FOR UPDATE;
    PERFORM 1 FROM products WHERE product_id=p_product FOR UPDATE;
    INSERT INTO transactions(product_id,revision_no,buyer_id,request_key,request_fingerprint)
      VALUES(p_product,p_revision,p_buyer,p_key,p_fingerprint) RETURNING transaction_id INTO result_id;
    RETURN result_id;
END $$;
CREATE FUNCTION transition_order(p_order bigint,p_status text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE pid bigint;
BEGIN
    SELECT product_id INTO pid FROM transactions WHERE transaction_id=p_order;
    IF pid IS NULL THEN RAISE EXCEPTION 'Order not found' USING ERRCODE='P0002'; END IF;
    PERFORM 1 FROM products WHERE product_id=pid FOR UPDATE;
    PERFORM 1 FROM transactions WHERE transaction_id=p_order FOR UPDATE;
    UPDATE transactions SET status=p_status WHERE transaction_id=p_order;
END $$;

CREATE FUNCTION expire_unanswered_orders(p_limit integer DEFAULT 100) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE entry record; n integer:=0;
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>1000 THEN RAISE EXCEPTION 'Batch size must be 1..1000'; END IF;
    PERFORM set_config('app.actor_id','',true);
    PERFORM set_config('app.system_action','order_expiry',true);
    PERFORM set_config('app.action_reason','Unanswered order exceeded configured expiry interval',true);
    FOR entry IN SELECT t.transaction_id FROM transactions t JOIN products p USING(product_id)
      WHERE t.status='placed' AND t.created_at<=clock_timestamp()-(SELECT unanswered_order_timeout FROM marketplace_settings WHERE singleton)
      ORDER BY p.product_id LIMIT p_limit FOR UPDATE OF p SKIP LOCKED
    LOOP
        PERFORM transition_order(entry.transaction_id,'cancelled'); n:=n+1;
    END LOOP;
    RETURN n;
END $$;
REVOKE ALL ON FUNCTION expire_unanswered_orders(integer) FROM PUBLIC;

CREATE FUNCTION validate_report() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p products%ROWTYPE;
BEGIN
    SELECT * INTO p FROM products WHERE product_id=NEW.product_id;
    IF TG_OP='INSERT' THEN
        IF app_actor_id() IS DISTINCT FROM NEW.reporter_id OR NEW.reporter_id=p.seller_id
           OR NOT is_member(NEW.reporter_id,'buyer') OR NEW.status<>'pending' OR NEW.assigned_admin_id IS NOT NULL
           OR NOT EXISTS (SELECT 1 FROM users WHERE user_id=NEW.reporter_id AND status='active' AND is_active)
           OR (NEW.transaction_id IS NULL AND NEW.revision_no IS DISTINCT FROM p.current_revision_no) THEN
            RAISE EXCEPTION 'Invalid report author/target/initial state' USING ERRCODE='23514';
        END IF;
    ELSE
        IF (to_jsonb(NEW)-ARRAY['status','assigned_admin_id','public_outcome','resolved_at']) IS DISTINCT FROM
           (to_jsonb(OLD)-ARRAY['status','assigned_admin_id','public_outcome','resolved_at']) THEN
            RAISE EXCEPTION 'Report submission is immutable' USING ERRCODE='23514';
        END IF;
        PERFORM require_admin_actor(); PERFORM require_action_reason();
        IF NEW.status IS DISTINCT FROM OLD.status AND NOT
          ((OLD.status='pending' AND NEW.status IN ('reviewing','resolved','dismissed'))
           OR (OLD.status='reviewing' AND NEW.status IN ('resolved','dismissed'))) THEN
            RAISE EXCEPTION 'Invalid report transition' USING ERRCODE='23514';
        END IF;
        NEW.resolved_at := CASE WHEN NEW.status IN ('resolved','dismissed') THEN coalesce(OLD.resolved_at,clock_timestamp()) END;
    END IF;
    IF NEW.assigned_admin_id IS NOT NULL AND NOT is_member(NEW.assigned_admin_id,'administrator') THEN
        RAISE EXCEPTION 'Report assignee must be administrator' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER report_guard BEFORE INSERT OR UPDATE ON fraud_reports FOR EACH ROW EXECUTE FUNCTION validate_report();
CREATE TRIGGER report_retained BEFORE DELETE ON fraud_reports FOR EACH ROW EXECUTE FUNCTION reject_history_change();
CREATE FUNCTION validate_attachment() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM fraud_reports WHERE report_id=NEW.report_id AND reporter_id=app_actor_id()
       AND status IN ('pending','reviewing')) THEN RAISE EXCEPTION 'Reporter and open case required' USING ERRCODE='42501'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER attachment_guard BEFORE INSERT ON report_attachments FOR EACH ROW EXECUTE FUNCTION validate_attachment();
CREATE TRIGGER attachment_immutable BEFORE UPDATE OR DELETE ON report_attachments FOR EACH ROW EXECUTE FUNCTION reject_history_change();

CREATE FUNCTION validate_review() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous moderation_reviews%ROWTYPE;
BEGIN
    IF NEW.reviewer_id IS DISTINCT FROM require_admin_actor() THEN RAISE EXCEPTION 'Reviewer actor mismatch' USING ERRCODE='42501'; END IF;
    PERFORM require_action_reason();
    PERFORM 1 FROM products WHERE product_id=NEW.product_id FOR UPDATE;
    SELECT * INTO previous FROM moderation_reviews WHERE product_id=NEW.product_id AND revision_no=NEW.revision_no
      ORDER BY reviewed_at DESC,review_id DESC LIMIT 1;
    IF (previous.review_id IS NOT NULL AND NEW.supersedes_review_id IS DISTINCT FROM previous.review_id)
       OR (previous.review_id IS NULL AND NEW.supersedes_review_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Correction must supersede latest decision on this revision' USING ERRCODE='23514';
    END IF;
    NEW.reviewed_at:=clock_timestamp();
    IF previous.reviewed_at IS NOT NULL AND NEW.reviewed_at<=previous.reviewed_at THEN
        RAISE EXCEPTION 'Decision chronology must advance' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER review_guard BEFORE INSERT ON moderation_reviews FOR EACH ROW EXECUTE FUNCTION validate_review();
CREATE TRIGGER review_immutable BEFORE UPDATE OR DELETE ON moderation_reviews FOR EACH ROW EXECUTE FUNCTION reject_history_change();

CREATE FUNCTION audit_core_change() RETURNS trigger LANGUAGE plpgsql AS $$
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
        before_record:=jsonb_build_object('status',OLD.status,'assigned_admin_id',OLD.assigned_admin_id);
        after_record:=jsonb_build_object('status',NEW.status,'assigned_admin_id',NEW.assigned_admin_id);
    ELSE
        target_review:=NEW.review_id; target_product:=NEW.product_id; action:='moderation_decision';
        after_record:=jsonb_build_object('verdict',NEW.verdict,'supersedes_review_id',NEW.supersedes_review_id);
    END IF;
    a:=require_admin_actor();
    INSERT INTO admin_audit_logs(admin_id,action_type,user_id,product_id,report_id,review_id,reason,before_data,after_data)
      VALUES(a,action,target_user,target_product,target_report,target_review,require_action_reason(),before_record,after_record);
    RETURN NULL;
END $$;
CREATE TRIGGER user_status_audit AFTER UPDATE ON users FOR EACH ROW EXECUTE FUNCTION audit_core_change();
CREATE TRIGGER product_visibility_audit AFTER UPDATE ON products FOR EACH ROW EXECUTE FUNCTION audit_core_change();
CREATE TRIGGER report_audit AFTER UPDATE ON fraud_reports FOR EACH ROW EXECUTE FUNCTION audit_core_change();
CREATE TRIGGER review_audit AFTER INSERT ON moderation_reviews FOR EACH ROW EXECUTE FUNCTION audit_core_change();
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON admin_audit_logs FOR EACH ROW EXECUTE FUNCTION reject_history_change();
CREATE TRIGGER users_retained BEFORE DELETE ON users FOR EACH ROW EXECUTE FUNCTION reject_history_change();
CREATE FUNCTION guard_registration_time() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.user_id<>OLD.user_id OR NEW.created_at<>OLD.created_at THEN
        RAISE EXCEPTION 'Registration identity and time are immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER registration_time_guard BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION guard_registration_time();
CREATE TRIGGER products_retained BEFORE DELETE ON products FOR EACH ROW EXECUTE FUNCTION reject_history_change();

CREATE FUNCTION validate_appeal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id bigint;
BEGIN
    SELECT p.seller_id INTO owner_id FROM moderation_reviews r JOIN products p USING(product_id) WHERE r.review_id=NEW.review_id;
    IF TG_OP='INSERT' THEN
        IF app_actor_id() IS DISTINCT FROM NEW.seller_id OR NEW.seller_id IS DISTINCT FROM owner_id OR NEW.status<>'pending' THEN
            RAISE EXCEPTION 'Appeal must be submitted by affected seller' USING ERRCODE='23514';
        END IF;
    ELSE
        IF (to_jsonb(NEW)-ARRAY['status','assigned_admin_id','outcome','resolved_at']) IS DISTINCT FROM
           (to_jsonb(OLD)-ARRAY['status','assigned_admin_id','outcome','resolved_at']) THEN RAISE EXCEPTION 'Appeal facts immutable' USING ERRCODE='23514'; END IF;
        PERFORM require_admin_actor(); PERFORM require_action_reason();
        IF OLD.status NOT IN ('pending','reviewing') THEN RAISE EXCEPTION 'Appeal is terminal' USING ERRCODE='23514'; END IF;
        NEW.resolved_at:=CASE WHEN NEW.status IN ('upheld','corrected','withdrawn') THEN clock_timestamp() END;
        INSERT INTO admin_audit_logs(admin_id,action_type,review_id,reason,before_data,after_data)
          VALUES(require_admin_actor(),'appeal_update',NEW.review_id,require_action_reason(),jsonb_build_object('status',OLD.status),jsonb_build_object('status',NEW.status));
    END IF;
    IF NEW.assigned_admin_id IS NOT NULL AND NOT is_member(NEW.assigned_admin_id,'administrator') THEN RAISE EXCEPTION 'Admin assignee required' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER appeal_guard BEFORE INSERT OR UPDATE ON seller_appeals FOR EACH ROW EXECUTE FUNCTION validate_appeal();

-- Available in the baseline; process grants are applied separately by 008.
CREATE FUNCTION enable_marketplace_role(p_role text) RETURNS void
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

COMMIT;
