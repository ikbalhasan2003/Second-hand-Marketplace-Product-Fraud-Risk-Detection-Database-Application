-- Run as the migration/test owner after install + seed + optional 008_privileges.sql.
-- Everything below rolls back. These are database-role tests, not browser authorization tests.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL ROLE secondhand_web;
SET LOCAL app.actor_id='3';
SET LOCAL app.action_reason='Database privilege regression';
SELECT place_order(3,102,1,'00000000-0000-4000-8000-000000002222',repeat('a',64));
INSERT INTO chat_messages(conversation_id,sender_id,message_text) VALUES(100,3,'Privilege test message');
DO $$ BEGIN
    BEGIN
        INSERT INTO users_groups(user_id,group_id) VALUES(3,3);
        RAISE EXCEPTION 'Expected denied direct role grant';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
    BEGIN
        INSERT INTO order_status_history(transaction_id,to_status,actor_id,reason) VALUES(100,'placed',3,'Forgery');
        RAISE EXCEPTION 'Expected denied direct history append';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
    BEGIN
        DELETE FROM admin_audit_logs;
        RAISE EXCEPTION 'Expected denied audit deletion';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
SET LOCAL app.actor_id='2';
DO $$ DECLARE pid bigint; BEGIN
    INSERT INTO products(seller_id) VALUES(2) RETURNING product_id INTO pid;
    INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,price,currency,condition,location,text_fingerprint)
    VALUES(pid,1,1,'Privilege fixture','Synthetic disposable listing',10,'USD','good','Demo City',repeat('b',64));
    UPDATE products SET current_revision_no=1,availability='available' WHERE product_id=pid;
    IF NOT EXISTS(SELECT 1 FROM risk_scan_jobs WHERE product_id=pid) THEN RAISE EXCEPTION 'Publication failed to queue'; END IF;
END $$;
SET LOCAL app.actor_id='1';
UPDATE users SET status='blocked' WHERE user_id=4;
UPDATE fraud_reports SET status='reviewing',assigned_admin_id=1 WHERE report_id=101;
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM admin_audit_logs WHERE user_id=4 AND action_type='account_status_change') THEN
        RAISE EXCEPTION 'Status change did not audit';
    END IF;
END $$;
RESET ROLE;
SET LOCAL ROLE secondhand_worker;
SELECT count(*) FROM claim_risk_job(interval '1 minute'); -- no registered fixture model: zero
DO $$ BEGIN
    BEGIN
        UPDATE risk_scan_jobs SET attempts=0;
        RAISE EXCEPTION 'Expected denied direct worker mutation';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
    BEGIN
        SELECT message_text FROM chat_messages LIMIT 1;
        RAISE EXCEPTION 'Expected denied private chat access';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
SET LOCAL ROLE secondhand_maintenance;
SELECT expire_unanswered_orders(10);
RESET ROLE;
SET LOCAL ROLE secondhand_training;
SELECT count(*) FROM dataset_records;
DO $$ BEGIN
    BEGIN
        SELECT email FROM users LIMIT 1;
        RAISE EXCEPTION 'Expected denied contact access';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
ROLLBACK;
\echo Database privilege regression passed.
