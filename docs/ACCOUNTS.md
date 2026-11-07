# Accounts and authorization

Buyer and seller registration create one normalized email identity and the selected marketplace membership. Existing members sign in and explicitly POST to `/account/enable/buyer/` or `/account/enable/seller/`. Login and app navigation do not grant membership. Administrator identities are separate and cannot gain marketplace memberships.

Provision an administrator with owner credentials:

```powershell
python manage.py provision_admin admin@example.invalid --name "Demo Administrator"
```

The command prompts privately for a validated password for a new identity. It is idempotent for the same active administrator and refuses marketplace identities or unreviewed replacement. Use `provision_admin --inspect` first; [Step 4](STEP_4_ACCOUNTS.md) documents reviewed transitions and the local source-file conflict. No password is accepted on the command line or committed. BCrypt SHA256 hashing, normalized email lookup and generic login errors apply. Public forms never accept privileged flags.

`/account/` changes passwords through Django APIs. The current session is rotated; other sessions fail their authentication hash check on the next request. Logout requires CSRF-protected POST. Session cookies are HttpOnly and SameSite=Lax; secure cookies apply outside debug mode. Login attempts are throttled by direct remote IP and normalized email in shared PostgreSQL counters. Reverse proxies must establish trusted remote addresses without trusting arbitrary forwarded headers.

Protected views check active authentication, app role, marketplace status and object participation. Blocking/deactivation preserves reads and existing order obligations, while new purchases, publication, chat and role enabling remain restricted. `is_active=false` disables all authenticated access. See [configuration decisions](CONFIGURATION.md).

Focused PostgreSQL tests verify duplicate emails, role escalation, CSRF, password session invalidation and restricted-account access. The separate buyer/seller/admin suites check object ownership.

Buyer registration, seller contact onboarding, shared routes and account appeals are documented in [the current operating guide](OPERATIONS.md).
