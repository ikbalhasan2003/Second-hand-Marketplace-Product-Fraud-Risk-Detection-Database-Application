# Accounts, onboarding, and administrator provisioning

Buyer registration requires email, password and password confirmation. A random display name is generated; no address or contact details are requested. Email is normalized and protected by the existing case-insensitive database uniqueness constraint. Django password validators and BCrypt SHA256 hashing apply.

Seller registration additionally requires a seller display name (public listing identity), city/service area (delivery context), and private contact email or telephone (account support). No street address or unnecessary legal identity is collected. Contact is not included in public listing templates. These existing users columns are reused; no destructive profile migration is necessary.

An existing buyer signs in at /login/, visits Account, and completes /account/enable/seller/. The profile update and seller membership addition commit together on the same user ID, preserving buyer membership, orders and history. Existing seller memberships are retained without forced re-onboarding. Shared sign-in never grants a membership. Seller-only members land at /sell/; buyers and dual-role members land at /. Navigation reflects membership. Administrator identities remain disjoint from marketplace identities.

## Trusted provisioning

Run migrations using the database owner, never the restricted web login:

```powershell
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py provision_admin --inspect
.venv/Scripts/python.exe manage.py provision_admin --credentials-file "Problem for update.txt"
```

The credential source is local, ignored by Git, and never logged. Alternatively supply an email and --name and enter the password at the hidden prompt. Passwords are hashed and validated; startup does not provision or rotate credentials.

If any other administrator/staff/superuser exists, provisioning refuses changes. Review the inspection output, preserve their user records and historical references, verify replacement access and recovery arrangements, then explicitly supply the exact IDs and an operator reason:

```powershell
.venv/Scripts/python.exe manage.py provision_admin --credentials-file "Problem for update.txt" --replace-admin-ids <reviewed-comma-separated-IDs> --reason "Reviewed administrator transition: operator and ticket"
```

The transaction creates the replacement with working credentials before removing previous administrator membership and staff/superuser flags. Other memberships, user records, passwords and history remain unchanged. An append-only administrator_transitions row records target, former IDs, timestamp and reason. A PostgreSQL advisory lock serializes provisioning. Failure rolls back the whole transition. Repeated provisioning of the same active administrator retains its password and does not duplicate audit events. An existing marketplace email cannot be promoted by this command; inactive or unusable existing administrator credentials require explicit recovery.

There is no public administrator registration or role-enabling endpoint. Public forms accept explicit fields only; is_staff, is_superuser and group payloads are ignored. Apply database/008_privileges.sql for restricted runtime credentials: the web role cannot write auth memberships, permissions, admin flags or provisioning audit rows. Sole administration is managed through this trusted command; database owners remain trusted and can bypass application controls. Do not use seed_demo after replacing demo administrator access: it intentionally rejects changed demo memberships rather than recreating privileges.

Migration 0002 creates the provisioning audit table; 0003 protects recorded transitions against update/delete. No existing user or role membership is changed by migrations.

## Local transition review

Initial inspection found demo administrator user 3 and an existing seller identity at the requested administrator email (user 4). The approved replacement of user 3 alone was refused because promoting user 4 would conflict with its preserved seller membership. No credentials or memberships were changed by that attempt. The user chose to preserve seller user 4 and supplied a separate administrator email. The approved transition was completed: adminemail@gmail.com is the sole administrator; user 3 remains in the database with administrator/staff privileges removed. Seller user 4 retains its original identity, password and seller membership. The transition is recorded in administrator_transitions. Sign-in and repeat provisioning were verified without changing the new password or duplicating the audit event.

The original local credential file still names the preserved seller email. Do not rerun file-based provisioning against that identity. To verify the provisioned administrator idempotently, run `.venv/Scripts/python.exe manage.py provision_admin adminemail@gmail.com`. The original local file was left unchanged; its password was read privately for the approved provisioning action.
