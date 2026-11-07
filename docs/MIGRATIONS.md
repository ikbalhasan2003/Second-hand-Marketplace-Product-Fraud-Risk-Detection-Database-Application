# PostgreSQL migration authority

See [Step 10 reconciliation, executed upgrade/backup evidence and recovery](STEP_10_DATABASE_DEPLOYMENT.md)
for the 7 November 2026 deployment through marketplace 0011. Apply both reviewed
privilege scripts, 008 followed by 009, after migrating the application schema.

The runnable application uses **Django migrations as its only installation authority**.
Use PostgreSQL 18 and run `python manage.py migrate` against a new, empty database
with the controlled migration/owner connection. Do not run `database/install.sql`
on that database, and do not use `--fake` or `--fake-initial` to adopt an existing
reference installation.

Django's standard `contenttypes`, `auth` and `sessions` migrations create their
infrastructure. `accounts/0001_initial.py` creates the email-login user at `users`
with `user_id` as its primary key and the explicit `users_groups` and
`users_user_permissions` junction names. The user model was defined before this
first migration. The lower-email unique index and original status/name/email
checks remain enforced in PostgreSQL.

`marketplace/0001_initial.py` installs frozen, reviewed SQL from its adjacent
`sql/` directory inside Django's migration transaction. These are copies of
reference scripts 001â€“005, with the duplicate identity/authentication DDL removed,
the required identity database defaults/checks retained, and the explicit
marketplace-role function made available in the baseline. Groups are provisioned
without adding any user memberships. There is no pgvector dependency.

The same migration records domain ORM state through unmanaged models.
`risk/0001_initial.py` records the remaining risk/provenance mappings. Unmanaged
models are query/write mappings; they do not transfer schema authority to
`syncdb`. Later domain changes require a new reviewed SQL migration and matching
model/migration-state updates. Never edit an already applied SQL snapshot to
upgrade a database. Composite primary keys use Django 5.2's
`CompositePrimaryKey`; composite foreign references retain both scalar IDs and
the SQL-owned constraints. Historical joins must use both product and revision.

The SQL preserves the deferrable current-revision foreign key, immutable history,
partial indexes, full-text GIN index, views, transactional order functions,
lease/fencing worker functions, and audit/queue triggers. Initial migration
rollback is deliberately irreversible: retaining an error is safer than dropping
immutable application history. Recovery uses a coordinated backup, or a new
disposable database for development.

`database/install.sql` remains an **independent reference/test installation**, not
an application setup step. The direct SQL regression suite intentionally creates
a second empty database and exercises the reference schema. Script 006 is an
optional standalone fixture; the application provides its own controlled account
and demonstration provisioning. Never seed an application's working database
with SQL fixture users or manually reset its identity sequences.

## Process privileges

Apply `database/008_privileges.sql` separately using the controlled role-management
connection after migrations. It grants the existing web/worker/maintenance/training
group roles and hardens trigger execution. Provision separate login roles and
grant each only its process group. Keep owner and login credentials outside Git.
Application extension tables require the explicit grants recorded in their
deployment setup; do not grant blanket DML on all future tables. Runtime processes
must not own the schema or inherit the migration role. Trusted backend actor
context is required inside each mutation transaction; the database views do not
authorize an individual browser user.

## Verification executed on 4 November 2026

An isolated workspace PostgreSQL **18.6** server and Python **3.13** environment
ran the following checks successfully:

- Fresh Django migration installation, including accounts, stock Django
  infrastructure, frozen core/risk SQL, and application extension migrations.
- `manage.py makemigrations --check --dry-run --skip-checks`: no changes detected.
- The existing direct PostgreSQL regression suite: **25 tests passed**, including
  its independent-connection purchase race and worker fencing/recovery checks.
- Script 008 followed by `database/tests/check_privileges.sql`: process privilege
  regression passed in the separate disposable reference database.

These results verify database installation/integrity, not all HTTP permissions,
model accuracy, realistic performance, media backup or browser acceptance.


## Completed update operations

See [OPERATIONS.md](OPERATIONS.md) for current publication gates, separate scan/training/maintenance startup, export provenance, durable training triggers and explicit activation policy. See [SETUP.md](SETUP.md) for exact fresh-install/upgrade commands and [PROJECT_UPDATE_VERIFICATION.md](PROJECT_UPDATE_VERIFICATION.md) for measured evidence and operational limitations.
