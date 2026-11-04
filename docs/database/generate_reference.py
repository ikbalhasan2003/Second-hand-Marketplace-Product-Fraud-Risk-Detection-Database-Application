"""Regenerate the repository schema reference from its reviewed CREATE TABLE DDL.

This deliberately small parser supports the SQL style used in database/001,002,007.
It is a documentation helper, not a SQL syntax validator or migration runner.
Run: python docs/database/generate_reference.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "database"
DIAGRAMS = ROOT / "docs" / "diagrams"

PURPOSES = {
    "users": "Shared identity, Django credentials and marketplace account status.",
    "django_content_type": "Django model identities used by permissions.",
    "auth_permission": "Named permission scoped to a Django content type.",
    "auth_group": "Role/group names; buyer, seller and administrator are provisioned groups.",
    "auth_group_permissions": "Unique group-to-permission junction.",
    "users_groups": "Single source of user role/group membership.",
    "users_user_permissions": "Explicit Django per-user permission junction.",
    "django_session": "Django database-backed sessions; session payload is framework encoded.",
    "categories": "Reusable category identity and display metadata.",
    "marketplace_settings": "Singleton deployment policy: one currency, unanswered-order expiry and scheduled refresh timezone.",
    "products": "Stable listing identity, seller ownership and mutable workflow/context state.",
    "product_revisions": "Immutable listing content keyed by product and revision number.",
    "product_images": "Immutable per-revision image association and validated file metadata.",
    "conversations": "One private conversation per product/interested buyer pair.",
    "chat_messages": "Retained participant messages with recipient-controlled initial read receipt.",
    "transactions": "Purchase/fulfilment agreement against immutable listing terms; no payment verification.",
    "order_status_history": "Append-only initial order event and subsequent state transitions.",
    "fraud_reports": "Buyer allegation/case workflow against a specific revision.",
    "report_attachments": "Private evidence images, limited to three distinct positions per case.",
    "moderation_reviews": "Canonical append-only evidence-backed decision chain per revision.",
    "admin_audit_logs": "Append-only privileged-action accountability with typed target references.",
    "seller_appeals": "P1 seller challenge to a moderation decision; one open appeal per decision.",
    "notifications": "P1 in-app summary notices deduplicated per recipient/source event.",
    "feature_schemas": "Immutable versioned feature-extraction contract and implementation revision.",
    "dataset_sources": "Data origin, attribution and license/access provenance.",
    "dataset_versions": "Dataset build/freeze lifecycle and immutable export manifest identity.",
    "dataset_split_groups": "Connected seller/template/duplicate group assigned to exactly one partition.",
    "dataset_records": "Versioned frozen features, labels and per-record provenance.",
    "risk_models": "Trusted registered fitted model artifact and reproducibility metadata.",
    "model_evaluations": "Measured evaluation slices; metrics derive from authoritative confusion counts.",
    "risk_rulesets": "Versioned operating policy, feature compatibility and maximum score age.",
    "risk_rules": "Numeric rules/thresholds unique by key within their ruleset.",
    "risk_scan_jobs": "Durable at-least-once queue with pinned context/configuration and frozen features.",
    "risk_logs": "Append-only advisory prediction output, at most one per job.",
    "risk_rescan_campaigns": "Recoverable batch-rescan obligation with immutable event scope/cutoff.",
    "risk_rescan_events": "Durable campaign/product delivery receipt preserving deduplication.",
    "embedding_models": "P2 immutable embedding model/version/dimensionality metadata.",
    "review_embedding": "P2 review vectors linked to exact review/model and source fingerprint.",
}

FIELD_PURPOSES = {
    "user_id": "Shared user identity; role-specific meaning follows the relationship.",
    "email": "Trimmed login email; lower(email) is unique.",
    "password": "Django encoded password hash, never a plaintext password.",
    "full_name": "Account display name; no duplicate name uniqueness requirement.",
    "private_contact": "Private contact value, excluded from public profiles/ML exports.",
    "status": "Constrained workflow/account/queue state; see checks and trigger contract.",
    "state": "Configuration/dataset lifecycle state; see checks and immutability guard.",
    "is_active": "Authentication flag for users; catalog-enabled flag for categories.",
    "is_staff": "Django administration flag; not a substitute for administrator membership.",
    "is_superuser": "Trusted Django superuser flag; never client assignable.",
    "seller_id": "Owning/scoped seller identity; orders derive ownership from product.",
    "buyer_id": "Buyer participant/account identity.",
    "reporter_id": "Buyer who submitted the allegation and owns its private evidence.",
    "reviewer_id": "Administrator responsible for the decision.",
    "admin_id": "Administrator who performed the audited action.",
    "recipient_id": "User authorized to receive this in-app notice.",
    "assigned_admin_id": "Optional administrator assigned to the workflow.",
    "product_id": "Stable product identity; paired with revision_no for historical content.",
    "current_revision_no": "Current content pointer; paired with this product_id.",
    "revision_no": "Positive revision sequence unique within a product.",
    "context_version": "Assessment evidence/refresh generation, independent of content revision.",
    "availability": "draft/available/reserved/sold; synchronized with order state.",
    "visibility": "Public/seller/admin removal state, independent of availability.",
    "first_published_at": "Immutable first publication instant used by rolling-window features.",
    "text_fingerprint": "SHA-256 normalized-text fingerprint; extraction rules are versioned.",
    "created_xid": "Internal creation-transaction marker: image association inserts must occur in that transaction.",
    "price": "Positive exact decimal listing price at this revision.",
    "original_price": "Optional nonnegative comparison price, without a claim that it was verified.",
    "currency": "Uppercase three-letter currency code; publication service enforces demo configuration.",
    "condition": "like_new/good/fair/poor product condition at this revision.",
    "storage_key": "Generated immutable file locator; no user-supplied public evidence URL.",
    "content_sha256": "SHA-256 of the stored file contents.",
    "sort_order": "Bounded position, unique within its parent; implements image-count cap.",
    "content_type": "Allowed image MIME type; actual bytes still require Pillow validation.",
    "byte_size": "File size, one byte through 5 MiB.",
    "width": "Positive decoded image width in pixels.",
    "height": "Positive decoded image height in pixels.",
    "sender_id": "Message sender; trigger requires a live authorized participant.",
    "message_text": "Escaped-on-display message body, 1..4000 trimmed characters.",
    "request_key": "Client request UUID scoped to the buyer for order idempotency.",
    "request_fingerprint": "SHA-256 of canonical request data; mismatched key replay fails.",
    "from_status": "Prior order state; null only for the initial event.",
    "to_status": "New order state recorded by this immutable event.",
    "actor_id": "User actor, mutually exclusive with a system actor.",
    "system_actor": "Named scheduled/system actor when no browser-user actor applies.",
    "reason_code": "Controlled allegation category, independent of an adjudicated verdict.",
    "public_outcome": "Reporter-facing moderation outcome; exclude private internal evidence.",
    "verdict": "Human fraud/legitimate/unresolved decision; not a model score.",
    "evidence_summary": "Required evidence basis; absence/dismissal of reports is insufficient.",
    "supersedes_review_id": "Immediate predecessor in the same revision's decision chain.",
    "action_type": "Privileged operation kind used for audit and durable rescan obligations.",
    "before_data": "Bounded historical change evidence, excluding secrets/private messages.",
    "after_data": "Bounded historical change evidence, excluding secrets/private messages.",
    "source_event_key": "Stable source identity for retry/delivery deduplication.",
    "definition": "Versioned feature contract JSON object, validated by extractor implementation.",
    "code_revision": "Source revision used to construct/extract/train this artifact.",
    "source_type": "synthetic/project_review/external provenance category.",
    "attribution": "Source/author attribution retained with dataset provenance.",
    "license_access_notes": "License, permitted use or access restrictions; no inferred bulk-data right.",
    "source_uri": "Optional provenance locator, not a download guarantee.",
    "generator_version": "Synthetic dataset generator version, when used.",
    "seed": "Reproducible random seed.",
    "export_cutoff": "Frozen upper observation/decision cutoff for the dataset export.",
    "split_strategy": "Description of group/temporal holdout policy and manifest.",
    "manifest_key": "Stored dataset/split manifest locator.",
    "dataset_sha256": "Checksum of the frozen export.",
    "group_key": "Pseudonymous connected grouping identity within a dataset.",
    "partition": "train/validation/test/challenge split; dataset records derive it from their group.",
    "record_key": "Stable record identity within the dataset version.",
    "seller_group_key": "Pseudonymous seller grouping key, excluding direct personal data.",
    "template_family_key": "Optional synthetic template/scenario family grouping key.",
    "duplicate_group_key": "Optional duplicate/variant grouping key for leakage checks.",
    "feature_as_of": "Point-in-time cutoff for frozen predictor facts.",
    "feature_values": "Frozen versioned feature vector; metadata/label fields are separate.",
    "label": "Eligible fraud/legitimate supervised target; unresolved records are excluded.",
    "label_source": "Decision/scenario source of the supervised target.",
    "label_decided_at": "When the label became known, distinct from predictor time.",
    "is_synthetic": "Explicit flag separating simulated records from real outcomes.",
    "scenario_version": "Generator/scenario version required for synthetic records.",
    "algorithm": "random_forest/logistic_regression/rules_baseline experiment method.",
    "artifact_key": "Immutable trusted model pipeline locator.",
    "artifact_sha256": "SHA-256 verified before loading the trusted artifact.",
    "class_mapping": "Saved class identity mapping including fraud class.",
    "dependency_manifest": "Exact training/inference package versions as structured metadata.",
    "slice_key": "Evaluation slice identity, such as synthetic/real/category.",
    "sample_count": "Measured number of evaluated examples.",
    "fraud_count": "Measured positive-label examples; equals TP + FN.",
    "true_positive": "Predicted fraud and labeled fraud examples.",
    "false_positive": "Predicted fraud and labeled legitimate examples.",
    "true_negative": "Predicted legitimate and labeled legitimate examples.",
    "false_negative": "Predicted legitimate and labeled fraud examples.",
    "average_precision": "Optional measured average precision in 0..1.",
    "report_key": "Evaluation-report artifact locator.",
    "max_assessment_age": "Maximum feature snapshot age for a result to remain current.",
    "rule_key": "Unique operating-rule key within the ruleset.",
    "numeric_value": "Rule value; published medium/high thresholds are validated together.",
    "attempts": "Execution/batch attempts; scan jobs permit at most three.",
    "claim_token": "Fresh UUID fencing token for the current processing lease.",
    "retry_at": "Earliest time queued work is eligible for claim.",
    "lease_expires_at": "Live processing lease expiry; expired claims cannot mutate through worker APIs.",
    "feature_snapshot": "Write-once vector, missing indicators and reference facts reused by retries.",
    "error_code": "Sanitized machine error code; no raw traceback/private payload.",
    "risk_score": "Advisory integer score in 0..100, not verified fraud probability.",
    "risk_level": "low/medium/high classification under the job's pinned ruleset.",
    "observed_factors": "Observed warning factors, separate from causal model explanations.",
    "model_explanation": "Optional structured explanation; never an unsupported fraud accusation.",
    "event_type": "Configuration/evidence/daily/manual reason for a durable rescan campaign.",
    "source_audit_id": "Required privileged source event except for the scheduled daily campaign.",
    "target_product_id": "Optional single-product campaign scope.",
    "cutoff_product_id": "Frozen maximum product ID, preventing retry scope expansion.",
    "cutoff_at": "Frozen campaign creation/scope instant.",
    "refresh_date": "Explicit calendar date forming a scheduled refresh event identity.",
    "refresh_timezone": "Explicit timezone defining the scheduled refresh date.",
    "cursor_product_id": "Monotonic committed batch cursor.",
    "session_key": "Framework session lookup token; never exported or logged.",
    "session_data": "Framework-encoded session payload.",
    "expire_date": "Session expiration instant for controlled cleanup.",
    "singleton": "Boolean primary key constrained true: at most one configuration row.",
    "unanswered_order_timeout": "Positive duration before an unanswered placed order may expire.",
    "refresh_timezone": "Configured timezone for deterministic daily-refresh date identity.",
}


def clean(sql):
    return re.sub(r"--[^\n]*", "", sql)


def split_top(text):
    parts, start, depth, quoted = [], 0, 0, False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'":
            if quoted and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            quoted = not quoted
        if not quoted:
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            elif ch == "," and depth == 0:
                parts.append(text[start:i].strip())
                start = i + 1
        i += 1
    if text[start:].strip(): parts.append(text[start:].strip())
    return parts


def table_blocks(sql):
    for match in re.finditer(r"CREATE\s+TABLE\s+(\w+)\s*\(", sql, re.I):
        start, depth, quoted, i = match.end(), 1, False, match.end()
        while i < len(sql) and depth:
            ch = sql[i]
            if ch == "'":
                if quoted and i + 1 < len(sql) and sql[i+1] == "'":
                    i += 2
                    continue
                quoted = not quoted
            if not quoted:
                if ch == "(": depth += 1
                elif ch == ")": depth -= 1
            i += 1
        yield match.group(1), sql[start:i-1]


def compact(s): return re.sub(r"\s+", " ", s).strip()


def parse():
    tables, sources, all_sql = {}, {}, ""
    for filename in ("001_core.sql", "002_risk.sql", "007_embeddings_optional.sql"):
        path = ROOT / "database" / filename
        if not path.exists(): continue
        sql = clean(path.read_text(encoding="utf-8"))
        all_sql += "\n" + sql
        for name, body in table_blocks(sql):
            fields, constraints, pk, fks = [], [], [], []
            for item in split_top(body):
                if re.match(r"(?:CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK)\b", item, re.I):
                    constraints.append(compact(item))
                    m = re.search(r"PRIMARY\s+KEY\s*\(([^)]+)\)", item, re.I)
                    if m: pk = [v.strip() for v in m.group(1).split(",")]
                    m = re.search(r"FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+(\w+)(?:\s*\(([^)]+)\))?", item, re.I)
                    if m: fks.append((tuple(x.strip() for x in m.group(1).split(",")),m.group(2),tuple(x.strip() for x in m.group(3).split(",")) if m.group(3) else (),compact(item)))
                    continue
                m = re.match(r"(\w+)\s+(.+)", item, re.S)
                if not m: raise ValueError(item)
                col, rest = m.groups()
                type_end = re.search(r"\s+(?:GENERATED|NOT\s+NULL|DEFAULT|PRIMARY\s+KEY|UNIQUE|REFERENCES|CHECK)\b", rest, re.I)
                typ = compact(rest[:type_end.start()] if type_end else rest)
                if re.search(r"PRIMARY\s+KEY", rest, re.I): pk.append(col)
                fm = re.search(r"REFERENCES\s+(\w+)(?:\s*\(([^)]+)\))?", rest, re.I)
                if fm: fks.append(((col,),fm.group(1),tuple(x.strip() for x in fm.group(2).split(",")) if fm.group(2) else (),compact(item)))
                dm = re.search(r"\bDEFAULT\s+(.+?)(?=\s+(?:CHECK|REFERENCES|UNIQUE|NOT\s+NULL)\b|$)", rest, re.I|re.S)
                default = "identity" if "IDENTITY" in rest.upper() else (compact(dm.group(1)) if dm else "—")
                fields.append({"name":col,"type":typ,"nullable":not bool(re.search(r"NOT\s+NULL|PRIMARY\s+KEY",rest,re.I)),"default":default,"sql":compact(item),"unique":bool(re.search(r"\bUNIQUE\b",rest,re.I))})
            for f in fields:
                if f["name"] in pk: f["nullable"] = False
            tables[name] = {"fields":fields,"constraints":constraints,"pk":pk,"fks":fks,"indexes":[]}
            sources[name] = filename
    # Explicit ALTER TABLE foreign keys, including current-revision and audit targets.
    for match in re.finditer(r"ALTER\s+TABLE\s+(\w+)\s+(.+?);",all_sql,re.I|re.S):
        table = match.group(1)
        if table not in tables: continue
        for part in split_top(match.group(2)):
            m = re.search(r"FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+(\w+)(?:\s*\(([^)]+)\))?",part,re.I)
            if m:
                tables[table]["fks"].append((tuple(x.strip() for x in m.group(1).split(",")),m.group(2),tuple(x.strip() for x in m.group(3).split(",")) if m.group(3) else (),compact(part)))
                tables[table]["constraints"].append(compact(part))
    for match in re.finditer(r"CREATE\s+(UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+(\w+)\s+(.+?);",all_sql,re.I|re.S):
        if match.group(3) in tables: tables[match.group(3)]["indexes"].append(compact(match.group(0)).rstrip(";"))
    for table in tables.values():
        table["fks"] = [(local,target,remote or tuple(tables[target]["pk"]),ddl) for local,target,remote,ddl in table["fks"]]
    return tables, sources


def purpose(col):
    if col in FIELD_PURPOSES: return FIELD_PURPOSES[col]
    if col.endswith("_id") or col == "id": return "Relational identifier; primary/foreign key role is shown alongside."
    if col.endswith("_at"): return "Recorded lifecycle instant; timestamptz stores an absolute point in time."
    if col == "version": return "Unique immutable version identity."
    if col in {"reason","description","comment","outcome","summary","title","name","location"}: return "Required/optional descriptive value; bounds and rules follow the SQL constraints."
    return col.replace("_"," ").capitalize() + "."


def write_dictionary(tables, sources):
    lines = ["# Database Data Dictionary", "", "Generated from the reviewed CREATE TABLE definitions with `python docs/database/generate_reference.py`. Exact DDL, indexes and checks are retained below. Trigger behavior is described in [Database Design](../../DATABASE_DESIGN.md) and the SQL function files. This generator documents SQL; it does not validate or execute it.", "", f"**Physical relations:** {len(tables)} tables including Django infrastructure, P1 structures, AI provenance, and optional P2 tables when present. Core scripts do not install the optional vector extension.", "", "All unqualified foreign keys use PostgreSQL's default `ON UPDATE NO ACTION`. An omitted delete clause means `ON DELETE NO ACTION`; explicit `RESTRICT` is shown. The current-revision foreign key is `DEFERRABLE INITIALLY DEFERRED`; other foreign keys are immediate unless SQL says otherwise.", "", "Nullability is physical SQL nullability. Additional relationships become mandatory in particular lifecycle states through checks/triggers. A field described as an identifier is explained by the Key/reference column and foreign-key list.", ""]
    for name, table in tables.items():
        lines.extend([f"## `{name}`", "", PURPOSES.get(name,""), "", f"**Source:** [{sources[name]}](../../database/{sources[name]}) · **Primary key:** `({', '.join(table['pk'])})`", "", "| Column | SQL type | Null? | Default | Key/reference | Purpose |", "| --- | --- | --- | --- | --- | --- |"])
        for field in table["fields"]:
            col=field["name"]
            keys=[]
            if col in table["pk"]:keys.append("PK")
            if field["unique"]:keys.append("UNIQUE")
            for local,target,remote,_ in table["fks"]:
                if col in local:keys.append(f"FK part → {target}({', '.join(remote)})")
            vals=[f"`{col}`",f"`{field['type'].lower()}`","yes" if field["nullable"] else "no",f"`{field['default']}`" if field["default"]!="—" else "—","; ".join(keys) or "—",purpose(col)]
            lines.append("| "+" | ".join(x.replace("|",r"\|") for x in vals)+" |")
        lines.extend(["", "**Checks, alternate keys and foreign keys**", "", "```sql"])
        for field in table["fields"]:
            if re.search(r"\bCHECK\b",field["sql"],re.I):lines.append(field["sql"])
        lines.extend(table["constraints"])
        for _,_,_,ddl in table["fks"]:
            if ddl not in table["constraints"]:lines.append(ddl)
        lines.extend(["```", ""])
        if table["indexes"]:lines.extend(["**Additional indexes**", "", "```sql",*table["indexes"],"```",""])
    (OUT/"DATA_DICTIONARY.md").write_text("\n".join(lines),encoding="utf-8")


def write_relations(tables,sources):
    lines=["# Relational Schema", "", "Notation: `PK` is the primary key, `AK` an alternate/unique key, and `FK` a foreign key. Nullable columns are marked `?` in relation signatures. Complete types, defaults, checks and indexes are in the [data dictionary](DATA_DICTIONARY.md).", "", "Every foreign-key component is significant. In particular, revision references use `(product_id, revision_no)`, not either field alone. All references retain history through `NO ACTION` or explicit `RESTRICT`; the product's current-revision reference alone is deferred to transaction end.", ""]
    for name,table in tables.items():
        lines.extend([f"## `{name}`", "", "```text", f"{name}(", "  "+",\n  ".join(f["name"]+("?" if f["nullable"] else "") for f in table["fields"]), ")", f"PK ({', '.join(table['pk'])})"])
        for local,target,remote,_ in table["fks"]:lines.append(f"FK ({', '.join(local)}) REFERENCES {target}({', '.join(remote)})")
        for c in table["constraints"]:
            if re.search(r"\bUNIQUE\s*\(",c,re.I):lines.append("AK "+compact(c))
        for f in table["fields"]:
            if f["unique"]:lines.append(f"AK UNIQUE ({f['name']})")
        for idx in table["indexes"]:
            if idx.upper().startswith("CREATE UNIQUE INDEX"):lines.append("CONDITIONAL/EXPRESSION AK: "+idx)
        lines.extend(["```", ""])
    lines.extend(["## Read models", "", "| View/function | Meaning |", "| --- | --- |", "| `risk_score_history` | Every successful prediction joined to its pinned target/configuration |", "| `fraud_logs` | Historical high-risk AI predictions; does not mean confirmed fraud |", "| `current_listing_risk` | Read-time current score and five assessment states |", "| `effective_reviews_at(cutoff)` | Canonical latest decision per revision as known by cutoff, including unresolved |", "| `latest_effective_reviews` | Canonical decisions as of the current statement |", "| `eligible_training_labels` | Latest evidence-backed fraud/legitimate decisions; unresolved is excluded |", "| `admin_review_queue` | One row per listing combining open cases and current high risk |", "| `seller_order_history` | Ordered revision terms and current order status; caller filters seller ownership |", "| `model_evaluation_metrics` | Precision, recall and F1 derived from stored confusion counts |", "", "Views do not provide per-browser-user authorization. They are internal query models, with runtime grants and authenticated query filters applied separately.", ""])
    (OUT/"RELATIONAL_SCHEMA.md").write_text("\n".join(lines),encoding="utf-8")


GROUPS = {
    "database-identity": ("Identity, Django infrastructure and deployment settings", ["users","auth_group","users_groups","django_content_type","auth_permission","auth_group_permissions","users_user_permissions","django_session","marketplace_settings"]),
    "database-marketplace": ("Listings, messaging and orders", ["users","categories","products","product_revisions","product_images","conversations","chat_messages","transactions","order_status_history"]),
    "database-moderation": ("Reports, moderation, audit and P1 extensions", ["users","products","product_revisions","transactions","fraud_reports","report_attachments","moderation_reviews","admin_audit_logs","seller_appeals","notifications"]),
    "database-ai-provenance": ("AI datasets, grouping, model provenance and evaluation", ["users","product_revisions","moderation_reviews","admin_audit_logs","feature_schemas","dataset_sources","dataset_versions","dataset_split_groups","dataset_records","risk_models","model_evaluations"]),
    "database-ai-execution": ("AI execution, versioned rules and rescan recovery", ["users","products","product_revisions","admin_audit_logs","feature_schemas","risk_models","risk_rulesets","risk_rules","risk_scan_jobs","risk_logs","risk_rescan_campaigns","risk_rescan_events"]),
    "database-embeddings": ("Optional P2 review embeddings", ["users","moderation_reviews","embedding_models","review_embedding"]),
}


def unique_subset(table, columns):
    candidates = [set(table["pk"])]
    candidates += [{f["name"]} for f in table["fields"] if f["unique"]]
    for constraint in table["constraints"]:
        match = re.search(r"\bUNIQUE\s*\(([^)]+)\)",constraint,re.I)
        if match: candidates.append({v.strip() for v in match.group(1).split(",")})
    return any(key and key <= set(columns) for key in candidates)


def mermaid(tables,names):
    names=[n for n in names if n in tables]
    lines=["erDiagram"]
    for name in names:
        table=tables[name]
        foreign={c for local,_,_,_ in table["fks"] for c in local}
        selected=[f for f in table["fields"] if f["name"] in table["pk"] or f["name"] in foreign or f["name"] in {"status","state","email","title","version","risk_score","claim_token","partition","source_event_key","context_version"}]
        lines.append(f"    {name} {{")
        for f in selected:
            typ=re.sub(r"[^a-zA-Z0-9_]","",f["type"].split("(")[0]).lower()
            key=", ".join(k for k,yes in [("PK",f["name"] in table["pk"]),("FK",f["name"] in foreign)] if yes)
            lines.append(f"        {typ} {f['name']}"+(" "+key if key else ""))
        lines.append("    }")
    for name in names:
        table=tables[name]
        for local,target,_,_ in table["fks"]:
            if target not in names:continue
            nullable=any(f["nullable"] for f in table["fields"] if f["name"] in local)
            parent="o|" if nullable else "||"
            unique=unique_subset(table,local)
            if target==name and "supersedes_review_id" in local:unique=True
            child="o|" if unique else "o{"
            label="_".join(local)
            lines.append(f'    {target} {parent}--{child} {name} : "{label}"')
    return "\n".join(lines)+"\n"


def write_diagrams(tables):
    DIAGRAMS.mkdir(parents=True,exist_ok=True)
    lines=["# Entity–Relationship Diagrams", "", "These diagrams map the physical PostgreSQL schema. They are split for readable assessment and printing; together they cover every base table, including Django infrastructure and optional extensions. Exact composite foreign keys, conditional uniqueness and checks are listed in the [relational schema](RELATIONAL_SCHEMA.md) and [data dictionary](DATA_DICTIONARY.md).", "", "**Legend:** `||` exactly one; `o|` zero or one; `o{` zero or many. The parent-side optional marker follows nullable foreign keys. A diagram showing zero children means a parent may exist before children are inserted; lifecycle checks can require a child later. PK/FK labels identify key columns. The deferrable product/current-revision relationship forms a deliberate cycle with product/revision ownership.", "", "A high-risk AI prediction is an observation. Confirmed fraud/legitimacy comes only from the moderation decision chain. `fraud_logs` and `risk_score_history` are views, so they do not appear as duplicate entities.", ""]
    for key,(title,names) in GROUPS.items():
        source=mermaid(tables,names)
        (DIAGRAMS/f"{key}.mmd").write_text(source,encoding="utf-8")
        lines.extend([f"## {title}", "", f"[Download Mermaid source](../diagrams/{key}.mmd)", "", "```mermaid",source.rstrip(),"```",""])
    lines.extend(["## Cardinality refinements", "", "- `products → product_revisions`: a draft can exist without a revision; publication requires a valid current revision. Both product ID and revision number participate in every historical link.", "- `transactions`: the product can have several cancelled orders, but a partial unique index permits at most one non-cancelled order, including a completed sale.", "- `product_images` and `report_attachments`: bounded unique positions enforce at most six listing images and three private attachments respectively.", "- `risk_scan_jobs → risk_logs`: a job has zero or one result and a deferred consistency trigger requires the result and succeeded state to commit together.", "- `moderation_reviews`: partial root uniqueness and predecessor uniqueness form one nonbranching chain per revision; a correction must name the current chain head.", "- `risk_models`/`risk_rulesets`: there may be many registered versions, but each has at most one active row, and active configuration must be compatible.", "- Campaign/product receipts are many-to-many membership records, with `(campaign_id, product_id)` as their composite primary key.", "- `django_session` has no user foreign key because Django stores framework session data; authorization must decode/validate it through Django.", "", "Regenerate these sources after schema edits with `python docs/database/generate_reference.py`. Mermaid renders in Markdown viewers that support it. The source files can also be imported into Mermaid tooling for SVG/PDF export.", ""])
    (OUT/"ER_DIAGRAM.md").write_text("\n".join(lines),encoding="utf-8")


if __name__=="__main__":
    OUT.mkdir(parents=True,exist_ok=True)
    tables,sources=parse()
    write_dictionary(tables,sources)
    write_relations(tables,sources)
    write_diagrams(tables)
    print(f"Generated dictionary, relational schema and {len(GROUPS)} ERD sources for {len(tables)} tables.")
