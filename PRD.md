# Second-hand Marketplace & Product Fraud Risk Detection Database Application

Course: Database Application Project Development
DBMS: PostgreSQL
AI Module: Custom-trained Random Forest fraud risk classifier
AI Language: Python
Language Backend:
Frontend:
AI Library: scikit-learn (free and open source)

>
> Core AI feature: Automated fraud risk classification (satisfies course AI integration requirement)

## 1. Project Background & Motivation

Second-hand online marketplaces are popular for affordable used goods, but they suffer heavily from fraud: fake products, stolen goods, sellers taking prepayment without shipping, misleading descriptions, duplicate scam postings, fake accounts. Buyers have no simple way to judge trustworthiness before dealing. Manual moderation by admins is slow and cannot keep up with new listings.

This project builds a database-centric web platform where **every product and user activity is automatically assessed by an AI risk model**. The database stores all raw transaction data, user behaviour features, AI prediction outputs, reports and audit trails. The system does not fully block listings automatically (to avoid false positives) but generates visible warnings and prioritizes suspicious items for human admin review.

### Business & Academic Goals

1. Design a fully normalized relational database (3NF) with ER diagram, DDL, triggers, check constraints, foreign key cascading rules.
2. Develop a working second-hand marketplace core workflow: user registration, product posting, search, chat, order, report.
3. Integrate AI fraud classification model that reads structured features from the database, outputs risk score + risk explanation, and writes results back into DB.
4. Build admin dashboards for risk monitoring, fraud report handling and rule adjustment.
5. Demonstrate dataset preparation workflow: public fraud datasets + synthetic local marketplace data for model training and validation.
6. If using an open-source marketplace base: perform schema redesign + add AI risk module, maintain before/after comparison in report.

## 2. User Roles, Detailed User Profiles & User Stories

### 2.1 Buyer

**Profile**: General users looking to buy used phones, laptops, furniture, bikes, books etc.
Needs: Find cheap goods, avoid scams, communicate with sellers, track orders, report fraud.
User Stories:

- As a buyer, I can register an account with email and secure password.
- As a buyer, I can browse and filter products by category, price, location, condition.
- As a buyer, I can open a product page and clearly see AI risk level, risk score and warning reason.
- As a buyer, I can start a chat with the seller to ask questions.
- As a buyer, I can place an order for an available product.
- As a buyer, I can submit a fraud report against a product/seller after suspicious interaction, attach notes and screenshots.
- As a buyer, I can view my order history and the status of my submitted reports.
- As a buyer, I can update my profile and contact information.
- As a buyer, I cannot view sensitive admin data or modify risk rules.

### 2.2 Seller

**Profile**: Users who want to sell their unused second-hand items. May be genuine casual sellers or malicious scammers.
User Stories:

- As a seller, I can create and edit my product listing with title, description, category, price, condition and multiple images.
- As a seller, after submitting a product, the system immediately runs AI risk scanning and shows me the risk result.
- As a seller, I can reply to incoming chat messages from buyers.
- As a seller, I can view new orders and update order status (pending, shipped, completed, cancelled).
- As a seller, I can delete my own active listings.
- As a seller, if my account gets blocked by admin, I cannot post new products or chat.
- As a seller, I can view my sales history and previous risk logs of my listings.

### 2.3 Platform Administrator

**Profile**: Trusted moderator, manages platform safety, responds to AI alerts and user reports.
User Stories:

- As admin, I can log into a protected dashboard separated from regular user pages.
- As admin, I can view a risk summary dashboard: total products, medium-risk count, high-risk count, new fraud reports.
- As admin, I can filter risk logs by risk level, date range, category.
- As admin, I can open a high-risk listing, check the AI feature evidence (price anomaly, keyword flag, seller history).
- As admin, I can view all fraud reports submitted by buyers, assign status: Pending, Under Review, Resolved, Dismissed.
- As admin, I can block or unblock a user account, remove fraudulent product posts.
- As admin, every moderation action is saved automatically to audit log with admin ID and timestamp.
- As admin, I can adjust threshold values in risk rules table (e.g., change price deviation percentage that triggers medium risk).
- As admin, I can export fraud dataset CSV for model retraining.

### 2.4 Data Analyst (Optional role for project demo)

**Profile**: Works to improve the AI fraud model.
User Stories:

- As analyst, I can export labelled fraud records (product features + final admin verdict: scam / legitimate).
- As analyst, I can view statistical charts: fraud distribution by product category, scam rate by user registration age.
- As analyst, I can test new model versions locally and import prediction results back into risk_logs table for comparison.

## 3. Functional Requirements (Expanded)

### 3.1 Authentication & User Management Module

- Registration: email, hashed password, user type selection (buyer / seller), full name, location, contact.
- Login / Logout, session management.
- Password change.
- User status enum: `active`, `blocked`. Blocked users cannot create products, send messages or place orders.
- Soft delete support for users (keep historical transaction and fraud data, do not hard delete).
- Constraint: one email address cannot register multiple accounts.

### 3.2 Product Catalog Module

- Product fields: title, description, category_id, price, original_price (optional), product_condition (new-like, good, fair, poor), location, is_available.
- Multiple image support: one product → many image records (store image path in DB; actual image file in local storage).
- Search: full text search on title and description; filters: category, min price, max price, risk level.
- Product status: available, sold, removed_by_admin, removed_by_seller.
- Trigger: On product INSERT or UPDATE → automatically call AI risk prediction service and insert record into `risk_logs`.

### 3.3 Chat & Messaging Module

- 1-to-1 private chat between a buyer and seller.
- Each message: sender_id, receiver_id, message text, sent_time, is_read flag.
- Load conversation history between two users.
- Optional simple keyword scan (basic rule filter; heavy NLP is out of scope).

### 3.4 Transaction / Order Module

- Order created when buyer confirms purchase.
- Order fields: product_id, buyer_id, seller_id, order_time, order_status.
- Order status enum: `pending_payment`, `shipped`, `completed`, `cancelled`, `disputed`.
- One product can only have one active order at a time (constraint to prevent multiple buyers).
- Transaction record links to product, buyer, seller for later fraud analysis.

### 3.5 AI Fraud Risk Detection Module (Core)

#### Input Features extracted from database

1. Price ratio: listing price vs average market price of same category
2. Suspicious keyword count in description (predefined scam keyword list)
3. Seller historical features: total previous reports, number of high-risk posts, account age, posting frequency
4. Image count (0 images or too many copied images is a signal)
5. Location mismatch signal
6. Recent duplicate postings by same user

#### Algorithm, Library and Trained Model

- **Algorithm:** Random Forest, the machine-learning method used to learn patterns from labelled marketplace records.
- **Library:** scikit-learn, the Python toolkit used to train, evaluate, save and run the classifier.
- **Trained AI model:** The fitted Random Forest classifier produced by training on the project's dataset. This trained model predicts fraud risk for new listings; it is not a pretrained marketplace fraud model.
- Random Forest is the selected starting algorithm. Its suitability must be demonstrated through validation rather than assumed to be the best-performing option.

#### Model Training (Offline)

1. Prepare labelled records with structured listing and seller features. Use `legitimate` and `fraud` as target labels; exclude unresolved records from supervised training.
2. Use only information available at prediction time. Do not use the listing's later reports, final admin verdict or previous AI score as input features.
3. Separate training, validation and test data before fitting preprocessing or the classifier. Keep duplicate listings and related scenario variants in the same partition.
4. Train a scikit-learn `RandomForestClassifier` using Python. Handle class imbalance using training-data class weights where appropriate.
5. Evaluate fraud precision, recall, F1-score, average precision and the confusion matrix. Compare against a simple rule-based baseline; report synthetic-data and real-data results separately when available.
6. Save the fitted preprocessing and classifier together with their feature definitions, model version and dependency versions so the application can reproduce inference.

#### Model Prediction (Application Runtime)

1. Fetch structured features from PostgreSQL
2. Load the saved preprocessing and trained Random Forest classifier using scikit-learn, apply the same feature definitions used during training, and predict the fraud-class score.
3. Convert the fraud-class score to a 0–100 risk score and assign a risk level. Store observed warning factors separately from model explanations; rule-based warnings must not be presented as proof of why an individual model prediction occurred. The score is a risk indicator, not a verified real-world fraud probability without representative validation and calibration.
4. Write prediction result into `risk_logs` table, linked to product_id
5. Initial configurable business thresholds (to be evaluated on validation data):
   - Low Risk: 0–39 → Green label, normal display
   - Medium Risk: 40–74 → Orange warning label + notice for buyer caution
   - High Risk: 75–100 → Red strong warning, auto push to admin alert queue

>
> Important: AI is an assistant, not final judge. Admin’s manual review is ground truth. Admin final verdict can be stored for future model retraining.

### 3.6 Fraud Report Module

- Buyer creates fraud report: product_id, comment, attachment file path, report_time.
- Report status: pending, reviewing, resolved, dismissed.
- Link report to admin review log.
- After admin resolves, admin can mark the listing as confirmed fraud; this labelled data becomes training data.

### 3.7 Admin Audit & Risk Rule Module

- `admin_audit_logs`: admin_id, action_type, target_user_id / target_product_id, action_details, timestamp.
Action types example: block user, unblock user, delete product, dismiss report.
- `risk_rules`: store configurable threshold values (price deviation threshold, report count threshold etc.) so admin can tune without changing AI code.

## 4. Full Database Schema Details (10 Tables, 3NF)

1. `users` (user_id PK, email, password_hash, full_name, user_type, location, contact, status, created_at)
2. `categories` (category_id PK, category_name, description)
3. `products` (product_id PK, seller_id FK, category_id FK, title, description, price, original_price, product_condition, location, status, created_at, updated_at)
4. `product_images` (image_id PK, product_id FK, image_path, uploaded_at)
5. `chat_messages` (msg_id PK, sender_id FK, receiver_id FK, message_text, sent_at, is_read)
6. `transactions` (transaction_id PK, product_id FK, buyer_id FK, seller_id FK, order_status, created_at)
7. `risk_logs` (risk_id PK, product_id FK, risk_score, risk_level, risk_factors, predicted_at, admin_verdict: null / legitimate / fraud)
8. `fraud_reports` (report_id PK, product_id FK, buyer_id FK, report_comment, file_path, report_status, created_at, reviewed_by FK admin_id, reviewed_at)
9. `admin_audit_logs` (audit_id PK, admin_id FK, action_type, target_id, target_type, note, action_time)
10. `risk_rules` (rule_id PK, rule_name, threshold_value, description, updated_by, updated_at)

Constraints:

- Foreign keys with ON DELETE actions carefully defined
- CHECK constraints for risk score between 0 and 100
- ENUM constraints for status fields
- NOT NULL on critical fields
- Indexes: product search index, risk_level index, user email unique index

## 5. Dataset Section (Extended)

### Dataset Sources

1. **BBB Scam Tracker Dataset**: Free public dataset from Better Business Bureau. Contains real scam reports: scam type, victim location, scam description, reported date. Useful to extract scam keywords and fraud patterns.
2. **eBay Auction Fraud Dataset**: Open academic dataset for online auction fraud, includes fake bidding, non-delivery fraud patterns.

### Limitations

These datasets are not directly compatible with our table schema. They do not contain clean second-hand product price, seller account age, local product category data.

### Dataset Preparation Workflow

1. Load public datasets and extract fraud pattern rules, scam keywords.
2. Generate synthetic dataset using Python: synthetic buyers, sellers, product listings, normal listings and labelled fraud listings.
3. Combine public fraud pattern knowledge + synthetic structured records.
4. Split: Train set (70%), Validation (15%), Test set (15%).
5. After deployment, admin’s manual verdicts (`admin_verdict` column in risk_logs) will grow our labelled dataset continuously for incremental retraining.

## 6. Non-Functional Requirements (Expanded)

1. **Normalization**: Schema strictly follow 3NF, eliminate update anomaly, insertion anomaly, deletion anomaly. ER diagram must show all entities, attributes, relationships, cardinality.
2. **Data Integrity**: Primary key, foreign key, check, unique, not null constraints implemented in DDL.
3. **Performance**: Index on frequently queried fields (product title, risk_level, user_id). For course scale, data volume is small.
4. **Security**: Password never stored plaintext; use bcrypt hash. Admin routes protected by authorization check. Blocked user access control.
5. **Maintainability**: Loose coupling: database layer, marketplace business layer, AI prediction layer separated. AI model logic is separate from SQL queries.
6. **Explainability**: AI output stores risk factors, not just a score. The report needs to explain why a listing got high risk. This is good for your course presentation.
7. **Backup**: Important tables (transactions, fraud_reports, risk_logs, audit_logs) should not be truncated easily.
8. **Usability**: Risk warning is prominent on UI; admin dashboard prioritizes high-risk alerts at top.

## 7. Out of Scope (Clear boundary for report)

- Real payment gateway, actual money transfer
- SMS/email notification service
- Real image recognition / deep image fake detection
- Mobile native application
- Advanced vector search / RAG chatbot
- Live chat video
- Large scale production load handling
- Third-party identity verification (NID verification)

## 8. Risk & Limitation of the System (For your discussion chapter)

1. **False Positive**: Genuine cheap second-hand goods may be flagged medium/high risk automatically. Admin review is mandatory to reduce this issue.
2. **False Negative**: Sophisticated scammers can avoid keyword and price rules, AI may miss their fraud.
3. **Dataset bias**: Synthetic data may not fully represent real-world scam variety.
4. **Limited AI**: The model only uses structured tabular features; no deep text embedding in this version (you can mention this as future improvement).

## 9. Acceptance Criteria (Detailed)

1. ER diagram drawn, all entities and relationships correctly shown.
2. All DDL scripts execute successfully on PostgreSQL, constraints work.
3. User registration, login, product post, chat, order workflow works.
4. After product saved, AI risk prediction triggers automatically and record saved to `risk_logs`.
5. Buyer can view risk level and warning message on product page.
6. Buyer can submit fraud report.
7. Admin can view alert dashboard, filter risk logs, change report status, block users.
8. Every admin moderation action appears in audit log.
9. Dataset loading, Random Forest training and evaluation code can run separately. The application can load the saved scikit-learn preprocessing and classifier to predict risk for new listings, with model version and evaluation results documented.
10. Final report includes: schema design, AI integration part, dataset discussion, testing result, limitation, future work.

## 10. Future Enhancement Ideas (for report conclusion)

- Add text embedding / semantic search to detect copied scam descriptions.
- Integrate Text2SQL so admin can query fraud database with natural language.
- Add image duplicate detection to find stolen product photos.
- Add email notification for new high-risk alerts.
- Deploy simple analytics dashboard with charts.
