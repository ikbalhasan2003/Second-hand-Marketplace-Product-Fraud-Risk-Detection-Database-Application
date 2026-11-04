# Accounts and authorization

Buyer and seller registration create one normalized email identity and the selected marketplace membership. Existing members sign in and explicitly POST to `/account/enable/buyer/` or `/account/enable/seller/`. Login and app navigation do not grant membership. Administrator identities are separate and cannot gain marketplace memberships.

Provision an administrator with owner credentials:

```powershell
python manage.py provision_admin admin@example.invalid --name "Demo Administrator"
```

The command prompts twice for a password, runs Django password validation and refuses an existing identity. No password is accepted on the command line or committed. `PASSWORD_HASHERS` selects Django's bcrypt-SHA256 implementation. Browser login uses case-insensitive email lookup and generic errors. Public forms never accept privileged flags.

`/account/` changes passwords through Django APIs. The current session is rotated; other sessions fail their authentication hash check on the next request. Logout requires CSRF-protected POST. Session cookies are HttpOnly and SameSite=Lax; secure cookies apply outside debug mode. Login attempts are throttled by direct remote IP and normalized email in shared PostgreSQL counters. Reverse proxies must establish trusted remote addresses without trusting arbitrary forwarded headers.

Protected views check active authentication, app role, marketplace status and object participation. Blocking/deactivation preserves reads and existing order obligations, while new purchases, publication, chat and role enabling remain restricted. `is_active=false` disables all authenticated access. See [configuration decisions](CONFIGURATION.md).

Focused PostgreSQL tests verify duplicate emails, role escalation, CSRF, password session invalidation and restricted-account access. The separate buyer/seller/admin suites check object ownership.
