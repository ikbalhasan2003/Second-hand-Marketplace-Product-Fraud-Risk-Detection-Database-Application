-- Small, repeatable-identity demonstration fixture for a fresh database.
-- ALL people, listings, messages, reports and decisions below are synthetic.
-- Run once as the database owner after 001..005. Timestamps use the database clock.
-- '!' is a Django unusable password: these are not login credentials.
-- USD / Demo City are fixture values, not an approved deployment configuration.
-- No image/evidence/model files are invented. Zero-image listings are intentional.
BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL app.action_reason = 'Install synthetic database demonstration fixture';

INSERT INTO auth_group(id,name) VALUES (1,'buyer'),(2,'seller'),(3,'administrator');
INSERT INTO users(user_id,email,password,full_name,location,is_staff) VALUES
    (1,'admin@example.invalid','!','Demo Administrator','Demo City',true),
    (2,'seller@example.invalid','!','Demo Seller','Demo City',false),
    (3,'buyer.one@example.invalid','!','Demo Buyer One','Demo City',false),
    (4,'buyer.two@example.invalid','!','Demo Buyer Two','Demo City',false);
INSERT INTO users_groups(user_id,group_id) VALUES (1,3),(2,2),(3,1),(4,1);
INSERT INTO categories(category_id,name,description) VALUES
    (1,'Electronics','Synthetic demonstration category'),
    (2,'Furniture','Synthetic demonstration category'),
    (3,'Books','Synthetic demonstration category'),
    (4,'Clothing','Synthetic demonstration category'),
    (5,'Other','Synthetic demonstration category');

SET LOCAL app.actor_id = '2';
INSERT INTO products(product_id,seller_id) VALUES (100,2),(101,2),(102,2);
WITH fixture(product_id,category_id,title,description,price,condition) AS (
    VALUES
      (100::bigint,1::bigint,'Wireless headphones',
       'Lightly used headphones. Includes the charging cable. Collection can be arranged.',45.00::numeric,'good'),
      (101::bigint,2::bigint,'Office chair',
       'Adjustable office chair with visible wear. Buyer can inspect before collecting.',30.00::numeric,'fair'),
      (102::bigint,2::bigint,'Desk lamp',
       'Working desk lamp with adjustable neck. No photographs in this demo fixture.',12.00::numeric,'good')
)
INSERT INTO product_revisions(product_id,revision_no,category_id,title,description,
                              price,currency,condition,location,text_fingerprint)
SELECT product_id,1,category_id,title,description,price,'USD',condition,'Demo City',
       encode(sha256(convert_to(lower(title || ' ' || description),'UTF8')),'hex')
FROM fixture;
UPDATE products SET current_revision_no = 1,availability = 'available'
WHERE product_id IN (100,101,102);
-- Publication queues unbound jobs while no approved model/ruleset is active.

SET LOCAL app.actor_id = '3';
INSERT INTO conversations(conversation_id,product_id,buyer_id) VALUES (100,100,3);
INSERT INTO chat_messages(conversation_id,sender_id,message_text)
VALUES (100,3,'Is collection available this week?');
INSERT INTO transactions(transaction_id,product_id,revision_no,buyer_id,request_key,request_fingerprint)
VALUES (100,100,1,3,'00000000-0000-4000-8000-000000000100',
        encode(sha256(convert_to('buyer=3;product=100;revision=1','UTF8')),'hex'));
-- The order trigger reserves product100 and appends its initial history event.

SET LOCAL app.actor_id = '2';
INSERT INTO chat_messages(conversation_id,sender_id,message_text)
VALUES (100,2,'Yes. Please suggest a collection time.');

SET LOCAL app.actor_id = '4';
INSERT INTO fraud_reports(report_id,product_id,revision_no,reporter_id,reason_code,comment)
VALUES (100,101,1,4,'misleading_description',
        'Synthetic case: please review whether the described wear is sufficiently clear.'),
       (101,102,1,4,'other',
        'Synthetic pending case: more information is requested; this is not a confirmed fraud label.');

SET LOCAL app.actor_id = '1';
SET LOCAL app.action_reason = 'Review synthetic scenario specification for the course demonstration';
UPDATE fraud_reports SET status = 'reviewing',assigned_admin_id = 1 WHERE report_id = 100;
INSERT INTO moderation_reviews(review_id,product_id,revision_no,report_id,reviewer_id,
                               verdict,reason,evidence_summary)
VALUES (100,101,1,100,1,'legitimate',
        'The synthetic scenario specifies a genuine worn chair with an accurate description.',
        'Evidence source: this deterministic fixture scenario. This is a simulated label, not a real-world finding.');
UPDATE fraud_reports SET status = 'resolved',
    public_outcome = 'Synthetic demonstration review completed.',resolved_at = clock_timestamp()
WHERE report_id = 100;

-- Explicit fixture IDs must not leave identity sequences behind the inserted rows.
SELECT setval(pg_get_serial_sequence('auth_group','id'),(SELECT max(id) FROM auth_group));
SELECT setval(pg_get_serial_sequence('users','user_id'),(SELECT max(user_id) FROM users));
SELECT setval(pg_get_serial_sequence('categories','category_id'),(SELECT max(category_id) FROM categories));
SELECT setval(pg_get_serial_sequence('products','product_id'),(SELECT max(product_id) FROM products));
SELECT setval(pg_get_serial_sequence('conversations','conversation_id'),(SELECT max(conversation_id) FROM conversations));
SELECT setval(pg_get_serial_sequence('transactions','transaction_id'),(SELECT max(transaction_id) FROM transactions));
SELECT setval(pg_get_serial_sequence('fraud_reports','report_id'),(SELECT max(report_id) FROM fraud_reports));
SELECT setval(pg_get_serial_sequence('moderation_reviews','review_id'),(SELECT max(review_id) FROM moderation_reviews));
COMMIT;
