# Seller App setup and verification

The Seller App uses the shared Django identity and PostgreSQL schema. Follow the root setup instructions, install pinned requirements, apply Django migrations as the migration owner and provision seller membership through registration or the authenticated account workflow. Run the web process with the restricted web credential; never give a browser a database credential.

## Implemented workflows

The dashboard at `/sell/` lists only the current seller's products, actual active/sold/current-high counts and status filters. The form at `/sell/listings/new/` and owner-scoped edit route saves incomplete private drafts or publishes complete immutable revisions. Revision/assessment history is read-only. Sales and existing buyer conversations reuse the shared order/chat views under seller role gates, including seller polling/read endpoints.

`app_listing_drafts` is application infrastructure, installed by migration `0003_listing_drafts`, rather than incomplete `product_revisions` rows. Its JSON payload contains bounded editable fields, private image metadata and image-retention choice. Every save checks the current revision plus draft version under account/product locks. Draft saving does not advance the public pointer or enqueue a scan. An active order, completed sale, administrator removal or restricted account prevents editing. Drafts may be read by their owner after marketplace restriction.

Publication validates a complete form, creates the next revision and all image associations, advances the product pointer and relies on existing SQL queue triggers in one transaction. Retained public images are checksum-verified and copied to newly generated immutable storage keys; historical files remain unchanged. Private draft images become verified public copies only during successful publication. New rollback files and consumed/discarded private draft images can be removed; referenced historical media is retained. If a process is interrupted between file creation and transaction completion, an unreferenced file may remain for a future reference-aware cleanup command. No P0 cleanup deletes historical evidence.

Image validation decodes JPEG/PNG/WebP with Pillow, rejects animation, malformed bytes, excess dimensions and file/count limits, strips embedded metadata by re-encoding, and ignores user filenames for storage. The first upload handler bounds actual streamed file bytes as well as ordinary Content-Length. Django bounds non-file form bytes. Configure the deployment reverse proxy's complete request-body limit to 32 MiB as well, so multipart overhead and malformed raw uploads are bounded before the app. Private draft images are served only through an owner-checked route with `private, no-store` caching.

The existing-case evidence endpoint at `/reports/<id>/evidence/` allows only the reporter to add files to an open case, including after blocking/deactivation. It locks the case, enforces three attachments total and uses private storage. New reports remain active-buyer-only. A reported seller cannot retrieve reporter-private evidence. Order-linked report forms display the purchased immutable revision.

## Checks executed

The focused suite runs with PostgreSQL, never SQLite:

```powershell
$env:DJANGO_DEBUG = 'true'
# Set PGHOST, PGPORT, PGUSER and PGDATABASE for a disposable migration-owner test environment.
.\.venv\Scripts\python.exe -m pytest tests/unit/test_uploads.py tests/integration/test_seller.py tests/integration/test_evidence.py -q --reuse-db
.\.venv\Scripts\python.exe -m ruff check seller_app marketplace/uploads.py marketplace/services/listings.py tests/unit/test_uploads.py tests/integration/test_seller.py tests/integration/test_evidence.py
```

The tests cover bounded decoding/storage integrity, streamed aggregate limits, private partial drafts, atomic publication/queueing, stale saves, immutable revisions, unauthorized/restricted edits, active-order locks, storage-failure rollback, private draft image access and existing-case evidence privacy. The delivery verification record contains final executed counts. Automated checks do not establish visual/browser accessibility acceptance or real-data model performance.

## Interface limits

The current form retains or removes all current-revision images together, and can discard all saved draft images. Individual drag/reorder editing and image previews are not yet implemented. Public/draft image lists display the actual stored order. A failed upload must be reselected by the browser. Private draft image metadata remains protected even when text validation fails; publication uses no invented assessment progress or score.

Current scan/publication, appeals and background process policy: [OPERATIONS.md](OPERATIONS.md). Public listing access requires a current successful scan; submitted does not mean publicly released.
