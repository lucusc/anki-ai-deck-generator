# Private temporary Blob storage (#18)

This slice is a production-SDK storage library and an inert-by-default retention
timer, **not an upload, job, quota or generation HTTP API**. It uses the existing
Functions module-root `auth.Principal` and `storage.Repository`. Future #7/#8
must invoke these operations only after authentication, capacity reservation and
accepted job ownership. There are no runtime agents or local-file deletion APIs.

## Namespace and access

One preprovisioned private container holds every temporary artifact class.
Names are derived internally:
`{userPartition}/{deckUUID}/{jobUUID}/{artifactClass}/{artifactUUID}`.
The partition is the accepted exact issuer/subject hash; mapping/job IDs are
validated canonical UUIDs, artifact IDs are assigned by the server. Callers
cannot supply a partition, container, path, URL or SAS to private operations.

`Artifacts.reserve()` durably registers a `b:{deck}:{job}:{class}:{artifact}`
row in the existing physical metadata Table, in a concrete-ETag deck-guard
transaction, before initializing Blob storage. Rows contain only UUIDs, class,
expiry, state, opaque Blob ETag and random lease ID; never content, names,
credentials or SAS URLs. `open -> stored` is a one-payload immutable publication.
No hashes, generation reservations, quotas or successful content validation are
invented here. Initial uploads are authorized against a queued job ETag; worker
artifacts require the current job ETag/token. Table fencing prevents stale
publication across reclaim/deletion, not cross-service atomicity.

Authenticated review access is an HTTPS **user-delegation, single-blob,
read-only SAS**, for at most five minutes and never past effective artifact
expiry. Results/review images must belong to a ready/completed job and a stored
artifact. A SAS is bearer access, not authentication of its eventual holder;
protect it in memory, never persist/log it, and never share it. It cannot list,
write, delete, lease or create anything. An issued read SAS is not individually
revoked by Table state: it lasts until its expiry or physical Blob deletion.
Bytes already downloaded or a read already in progress cannot be recalled.
Worker downloads use a concrete Blob ETag and a bounded read.

**There is no write SAS.** Upload bytes will be mediated by authenticated server
code in #7. This is permitted by that issue's “file uploads or narrowly scoped
upload authorization” criterion. Direct-upload grants must not be bolted onto
this protocol: ordinary write SAS permits operations that bypass application
ETag/lease discipline. An account-wide delegation-key revocation is not a narrow,
immediate per-artifact fence.

## Supported deletion protocol

1. Register an `initializing` artifact in a fenced Table transaction.
2. Make exactly one create-only **zero-byte** `Put Blob` with `If-None-Match: *`,
   then acquire an infinite Blob lease using the registered random ID. Disable
   automatic SDK retries. Only after both calls acknowledge, persist `open`
   and the placeholder ETag. No study content is sent during initialization.
3. Every content write is a single bounded `Put Blob` with that lease ID and
   concrete `If-Match`; there are no block-staging, copy, snapshot or naked
   create-content operations. The initial transport ceiling is **16 MiB per
   artifact**, not an accepted total upload/archive-expansion quota. A failed or
   ambiguous publication is not reported as successful; allocate a new artifact
   identity only after deliberately reconciling/cleaning the old attempt.
4. For artifact deletion, fence the row as `deleting`; for deck deletion, first
   persist the accepted minimal `deleting` mapping. New Table-authorized work
   is rejected. Delete the Blob using its lease ID, **without a stale ETag**:
   a PUT winning before deletion is removed by deletion; a later PUT with the
   old lease and `If-Match` cannot create a missing blob. Do not release/break
   the lease and leave a writable content blob behind.
5. Only after acknowledged physical deletion (or specifically `BlobNotFound`)
   remove the artifact row in a fenced Table transaction. An outage, missing
   container, lease mismatch or retained version propagates; retry keeps the
   guard. A lost Table acknowledgement is recoverable: retry Blob deletion,
   accept `BlobNotFound`, then conditionally remove the row.
6. Final Table deletion refuses any remaining `b:` rows. Cleanup/finalization is
   bounded and returns `False` when another pass is needed. New mapping UUIDs
   are never recycled.

An initializer racing deletion still has a durable row. It must acknowledge its
empty-create/lease calls before settling that row as `deleting`; cleanup can then
remove it. **An ambiguous create/lease call or initializer death is a safety
blocker, not an automatically drained operation.** Do not erase its record based
on an elapsed clock, HEAD probe, or a guessed HTTP timeout. Keep the deleting
guard, deny content access, and alert for reconciliation of the original
initializer/server requests. An active initializer that loses its final Table
acknowledgement also needs explicit reconciliation; never repeat initialization
with a new create request. This slice has no automatic unknown-initializer
resolution API. A future operator procedure must demonstrate request settlement
and safe placeholder cleanup before clearing that guard.

This deliberately avoids a false bounded-time drain claim. Microsoft documents
PUT timeouts as **10 minutes per MiB**, an exception to the nominal 30-second
timeout; client read timeout does not prove a server PUT has stopped. Under the
documented conditional Blob operations, physical deletion invalidates content
write authority rather than waiting out a writer/SAS. Real streaming-PUT/delete
interleavings still require the cloud smoke test below.

## Retention and lifecycle integration

| Data | Maximum | Application cleanup |
| --- | --- | --- |
| Abandoned original uploads | Creation + 24h | Bounded inventory sweep |
| Failed-job files | Failure + 24h, never extending an existing artifact deadline | Failure timestamp/effective expiry + sweep |
| Originals/extraction-only intermediates | Initial 24h ceiling; processing completion ends retention | Immediately call `processing_completed()` after persisted READY transition; repeat bounded passes |
| Result JSON/review images/diagrams | Creation + 7d | Sweep; access denial after actual expiry requires re-upload |
| Imported backend payload/media | Committed acknowledgement + 24h, never extending earlier expiry | Persist COMPLETED after Anki commit, call `import_committed()` for immediate cleanup; sweep recovers missed callback |
| Operational Jobs/Documents/Cards and descriptive Deck metadata | Job/mapping creation + 30d | Conditional physical purge; deck reduced to minimal guard |
| Minimal imported source/card hashes/import IDs | Only while mapping exists | Physical deletion after Blob drain and mapping deletion |

`transition_job()` adds only retention event timestamps: `FailedAt`,
`ProcessingCompletedAt`, and `ImportCommittedAt`. These do not extend the
accepted operational deadline. Completed means committed Anki acknowledgement,
not generated results. Future partial-import/media integration must associate
each acknowledged payload/media set with its cleanup boundary; this library
does not infer a partial Anki commit or delete images still needed by unrelated
review operations. Existing card acknowledgement still caps its Table result
reference, but is not itself the whole-job media cleanup callback.

The monitored timer uses a deployment-controlled inventory of **1-5 exact
issuer/subject pairs**, not an account-wide user scan. Enrollment/removal must
maintain that complete inventory; removing a user before cleanup is unsafe.
Each invocation queries at most one **10-row SDK page per user**, persists
an opaque continuation in a content-free `r:retention` cursor, and uses bounded
10-child deletion passes. It stops starting new work after a 180-second
application budget, leaving host/runtime and per-request timeout failure
recovery explicit. A cursor advances only after successful page work.
One failing record/user does not prevent attempts for the other records/users.
Overdue cycles (15 minutes), failed cleanup, unavailable storage and pending
initializers raise a fixed content-free failure, rather than a successful timer.

Physical cleanup targets **one hour before maximum expiry** (23h / 6d23h /
29d23h) for scheduling/outage headroom. “Up to” is a maximum, not a promise of
availability until the last minute. Logical expiry and an `ExpiresAt` field are
not physical deletion. A disabled timer, omitted user, prolonged outage,
oversized inventory backlog, stuck initializer or missing monitoring can miss
retention deadlines. Alert on every timer failure and no successful cycle for
15 minutes; configure that external alert in #31/#34. Preserve cursor/guard
evidence and retry explicitly. **No unconditional exact-deadline physical
compliance, including 30-day retention, is certified by offline tests.**

Lifecycle rules in #34 are only an asynchronous backstop, not a substitute for
these callbacks/sweeps. Local original files and imported Anki media are never
touched. No archive, extra payload version, snapshot or copied result is created.

## Production configuration and policy

Scoped SDK dependencies are included by the existing backend manifest:
`azure-storage-blob`, `azure-mgmt-storage`, `azure-data-tables`, `azure-identity`.
Use `DefaultAzureCredential` with managed identity in Azure or an explicitly
supplied `TokenCredential`. There are no account keys or storage connection
strings in this library.

Configure credential-free HTTPS Table/Blob endpoints, table/container names,
subscription/resource-group/account identity and the private user inventory:
`STORAGE_TABLE_ENDPOINT`, `STORAGE_TABLE_NAME`, `STORAGE_BLOB_ENDPOINT`,
`STORAGE_BLOB_CONTAINER`, `STORAGE_SUBSCRIPTION_ID`, `STORAGE_RESOURCE_GROUP`,
`STORAGE_ACCOUNT_NAME`, `RETENTION_USERS`. The Blob endpoint must match the
configured account's public Azure endpoint; sovereign-cloud/HNS variants are
not accepted silently.

Production policy checking uses the **real ARM Storage Management SDK** because
the data-plane Blob SDK's service-properties deserializer omits versioning and
restore settings. Require private containers, account public access and Shared
Key disabled, non-HNS storage, versioning/automatic snapshots/soft-delete/
point-in-time restore disabled. Unknown versioning state fails closed.
Deletion also performs a bounded exact-artifact versions/deleted-copy listing
and refuses retained versions rather than pretending base deletion removed
them; snapshots are included in base deletion. Existing recovery copies must
be explicitly removed and verified by an operator. Do not enable extra-copy
features for disposable processing content: retained copies continue billing
and can break the specified maxima.

Grant narrowly scoped Blob/Table data permissions and user-delegation-key
generation permission. The SDK policy reader also needs management-plane
`Microsoft.Storage/storageAccounts/read` and
`Microsoft.Storage/storageAccounts/blobServices/read` at this account (a scoped
Reader role is a broader built-in alternative). Do not grant ListKeys or account
write/provisioning rights to make checks pass. Missing RBAC is a surfaced error.
The policy check is not an atomic lock against an administrator changing
resource configuration during an operation.

`RETENTION_SCHEDULE` is `0 */5 * * * *`; the example explicitly sets
`AzureWebJobs.retention_worker.Disabled=true` with empty storage/inventory values.
This task does not enable the timer, run a host, provision, deploy or make paid
calls. Enabling it requires operator authorization, complete inventory and
monitoring; an empty inventory fails explicitly, not as a no-op success.

## Evidence and remaining gates

Run `cd backend && .venv/bin/python -m pytest`. Synthetic atomic doubles cover
every artifact class, issuer/subject isolation, expiry, completion/acknowledgement,
immutable writes, stale workers, before/after-deletion writes, deletion retries,
lost Table acknowledgement, late/ambiguous initialization and paged physical
purge. Real SDKs use socket-free HTTP transports to verify lease/ETag headers,
single PUT, read SAS signing/expiry, policy reads, version checks, paging and
404/412/503 propagation. In-memory mutations of real source must break physical
deletion, exact expiry and the lease-header assertions.

Before acceptance/release, demonstrate a synthetic live Azure/host test with
managed identity and the intended policy/RBAC: private container denial;
single-blob read SAS scope/expiry; stalled streaming PUT versus DELETE on both
sides of the commit boundary; missing-lease/If-Match recreation denial; network
loss during empty create/lease and deletion; retained-copy inspection; complete
multi-user timer cycles; completion and committed-import callbacks; backlog/
outage alert/recovery within the actual maxima. Also resolve the unknown
initializer operator protocol and partial-import/media association in their
consumers. No Anki/cloud/provider/host test or infrastructure activation was
performed. Keep #18 and #21 acceptance gates explicit; this is reviewable
implementation evidence, not a full completion claim.

Microsoft sources checked 2026-11-21:
[Put Blob](https://learn.microsoft.com/rest/api/storageservices/put-blob),
[Lease Blob](https://learn.microsoft.com/rest/api/storageservices/lease-blob),
[conditional headers](https://learn.microsoft.com/rest/api/storageservices/specifying-conditional-headers-for-blob-service-operations),
[Delete Blob](https://learn.microsoft.com/rest/api/storageservices/delete-blob),
[timeout exceptions](https://learn.microsoft.com/rest/api/storageservices/setting-timeouts-for-blob-service-operations),
[user delegation SAS](https://learn.microsoft.com/azure/storage/blobs/storage-blob-user-delegation-sas-create-python),
[ARM Blob services](https://learn.microsoft.com/python/api/azure-mgmt-storage/azure.mgmt.storage.operations.blobservicesoperations).
