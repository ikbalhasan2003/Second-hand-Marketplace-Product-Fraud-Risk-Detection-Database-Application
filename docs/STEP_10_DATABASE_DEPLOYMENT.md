# Step 10: database reconciliation and deployment checks

Executed 7 November 2026 with PostgreSQL 18.6 and the project Python environment.
Django migrations remain the sole application schema authority. No previously
applied migration or frozen SQL file was edited.

## Schema audit and changes

Seller onboarding uses existing `users.full_name`, `location`, `private_contact`
and guarded `users_groups` membership. Administrator handover receipts remain in
`administrator_transitions` with the immutable-history trigger from accounts 0003.
Moderation uses the existing report states and immutable revision decisions;
marketplace 0007/0008 supply policy receipts and the protected policy audit trigger.
General account appeals and private evidence are SQL-owned tables from 0009;
their services intentionally use explicit SQL rather than unmanaged ORM models.
Training jobs and freeze/enqueue functions are SQL-owned structures from 0010.
Existing domain ORM mappings retain their unmanaged state and composite identities.

Added forward-only `marketplace.0011_deployment_integrity`, depending explicitly on
marketplace 0010, accounts 0003 and risk 0001. It adds appeal queue/reviewer/evidence
indexes and training queue/requester/audit/model indexes. It protects training
request configuration, dataset, requester, source receipt and creation facts from
updates, prohibits deletion, and freezes successful receipts. Mutable execution
fields remain available to the trusted trainer. It revokes PUBLIC execution on
new trigger helpers. No tables, columns, records or historical snapshots are dropped.

`database/009_app_privileges.sql` now executes all extension grants in one
transaction, including scoped training UPDATE columns and candidate/evaluation/audit
INSERT privileges. The trainer can read only identity/status columns needed to
validate the requesting administrator, not private contacts, passwords, chats or
evidence. It cannot UPDATE/activate models, delete jobs, change request configuration,
or execute private trigger helpers. Web reads training status and enqueues through
the administrator-validated function; it cannot directly UPDATE training jobs.
Worker and maintenance roles receive no appeal/training extension access.
There are no blanket future-table or default EXECUTE grants.

Deployment order: Django migrations, `database/008_privileges.sql`, then
`database/009_app_privileges.sql`, using the controlled owner/role-management
connection. Reapply the two reviewed scripts on a fresh installation even when
the process roles did not exist when migrations ran. Configure separate process
LOGIN roles inheriting their NOLOGIN groups; the training connection uses
`REGISTRATION_DATABASE_URL` with the `secondhand_training` group.

## Fresh installation, upgrade, and existing records

Run the repeatable drill (credentials are read from Django configuration and
passed to PostgreSQL subprocesses only through their environment):

```powershell
.venv\Scripts\python.exe scripts/verify_migrations.py --pg-bin .local/pg-server/pgsql/bin
```

The script creates uniquely named databases without resetting existing databases.
It installs a fresh schema, upgrades an older marketplace 0004 schema containing
the adapted existing synthetic SQL fixture through 0010 and then the final leaf,
and applies process grants in both. It compares public columns/defaults,
constraints, indexes, functions and non-internal triggers: catalogs are identical.
It verifies unchanged revision, order-status, moderation and audit records, the
deferrable composite current-revision reference, and intentional NULL assessments
on legacy orders. It tests a two-connection race using `secondhand_web`: exactly
one open appeal commits and the other fails its unique constraint.

There is deliberately no fabricated historical assessment backfill: old purchases
keep NULL snapshots. There is no reconstruction of missing appeal evidence or
onboarding facts. Appeals/jobs begin empty for this legacy fixture. The training
freeze trigger applies to future building-to-frozen transitions; previously frozen
datasets are not silently trained. An administrator may explicitly request their
training through the existing idempotent enqueue operation. Historical labels,
revision composite references and immutable receipts are preserved.

Latest complete catalog/race drill: `runtime/migration-checks/7659495ce63c/report.json`.
Disposable databases are retained for inspection; their names are in the report.

## Working database: exact execution

Verified target: `secondhand_fraud`, local server `::1`, port `5432`, connection
role `postgres`. All migrations through marketplace 0010, accounts 0003 and risk
0001 were already applied before this step.

Before mutation, created a custom-format backup and successfully restored it with
`pg_restore --exit-on-error` into `step10_restore_0d19ce5352ad`. Compared the migration
ledger and users/products/orders/audit/training row counts with the source.

- Backup: `runtime/migration-checks/0d19ce5352ad/working-before.dump`.
- SHA-256: `c4b27eca616ce09ece119eacdbc29073463fde7d84b24e60c402b738a6c93132`.
- Applied migration: **marketplace.0011_deployment_integrity** only.
- Applied grants: **database/008_privileges.sql**, **database/009_app_privileges.sql**.
- Pending Django migrations afterward: **none**.
- Not applied: reference `database/install.sql`, seed SQL, optional pgvector schema;
  these are not application migration prerequisites.
- Private command log and report: `runtime/migration-checks/0d19ce5352ad/`.

The exact invocation was the drill above with `--apply-working`. That option runs
disposable checks first, then backs up/restores before migrating the configured
target. It requires database-creation, DDL and role-management privileges.
Backups and logs are ignored by Git and contain application data; retain them with
operator-only filesystem access and your normal encrypted off-host backup policy.

The current working connection is a superuser, not a production runtime login.
This step verifies process grants but does not replace local credentials or change
object ownership. A production deployment still needs a dedicated non-login owner
and separate web/worker/maintenance/training logins, as required by MIGRATIONS.md.
No production credential provisioning or optional pgvector validation is claimed.

## Irreversibility and recovery

SQL migrations 0001 and 0004 through 0011 intentionally have no destructive reverse
operation; 0002/0003 have historical no-op reverses, which must not be treated as a
schema rollback. A Django rollback cannot safely remove retained history. Prefer a
forward corrective migration for a fault. Do not edit applied snapshots or fake
the migration ledger.

For full recovery, stop web, risk worker, trainer and maintenance writes. Preserve
a new incident backup and retain all writes since the pre-change backup for
reconciliation. With the same controlled libpq connection settings and required
roles available, create a NEW recovery database and restore the custom archive:

```powershell
createdb step10_recovery
pg_restore --exit-on-error --dbname step10_recovery runtime/migration-checks/0d19ce5352ad/working-before.dump
```

Use the pre-0011 application revision for a preceding-schema recovery, validate
the ledger/history/counts and permissions, and reconcile subsequent writes before
pointing processes at the recovered database. Never restore over the working
database or use `--clean` as an automatic rollback. This migration changes only
database objects: existing private media and model/dataset artifacts must still be
retained under the project's coordinated filesystem backup policy.

## Automated validation

- Fresh and populated upgrade installations, full catalog equality, process-role
  allow/deny checks and independent-connection appeal race: passed.
- Pre-change working backup restore: passed; migration apply/check: passed.
- Django system check: no issues. Migration state check: no changes detected.
- Targeted Ruff: passed.
- Schema/accounts/appeals/training initial run: 36 passed in 35.60 seconds.
- Final training suite, including real fitting under `SET LOCAL ROLE
  secondhand_training` and immutable job provenance: 15 passed in 5.01 seconds.

Expanded schema/accounts/appeals/training/worker/buyer/seller/admin regression:
**100 passed in 41.55 seconds**. The exact command is recorded in
PROJECT_UPDATE_VERIFICATION.md.
These checks establish persistence and permissions, not production model accuracy
or a production runtime/ownership deployment.
