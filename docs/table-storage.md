# Table Storage contract (#21)

This is a storage library, not an upload/job API or a running retention service.
`backend/storage/azure.py` uses the production Azure Table SDK. The repository
takes the existing `backend/auth.py` `Principal` from the validated issuer/subject authentication
boundary; it never accepts identity headers or a caller-selected partition.

## Physical layout and access

Provision **one** physical Azure Storage table, for example `Metadata`, with
four logical entity types: Documents, Cards, Decks and Jobs. This deliberately
refines the architecture's conceptual store names, rather than provisioning
four separate tables and pretending their writes are transactional. Each
mutation of a deck's children includes a conditional replacement of its Decks
guard, **in the same table and user partition**. The guard's returned ETag is
opaque; replacing even unchanged properties advances it.

`PartitionKey` is `u` plus SHA-256 of the UTF-8 canonical JSON array
`["anki-tables-v1", issuer, subject]`. Both identity components are included,
case-sensitive and unmodified. Neither is stored in cleartext. This computes an
identity namespace, not document/card hashes (#19/#22).

All deck/job/document/card/import/artifact IDs are canonical lowercase UUIDs.
Decks and operational records receive server-generated UUIDs. Removed deck IDs
are never offered for recreation; choosing the same local Anki deck later creates
a **new mapping UUID**. A deck name or local integer ID is not an authorization
key. No cross-user/deck sharing or scan is implicit.

| Kind | RowKey | Properties and access |
| --- | --- | --- |
| Decks | `d:{deck}` | Active/deleting guard and logical mapping UUID. Optional opaque subject/chapter UUIDs, created/updated/expiry timestamps for at most 30 days; then only mapping/guard keys and state. List by user + `d:` range. |
| Jobs | `j:{deck}:{job}` | Settings fingerprint SHA-256, lifecycle, numeric usage counts, duration, timestamps, lease token/deadline and optional result reference. Point get or user/deck `j:` range. |
| Documents | `o:{deck}:{document}` | Owning job/deck, source SHA-256, compatibility SHA-256, state, extraction/prompt/model versions, native/ocr/none method and numeric page/slide/section coordinates; optional original reference. Point get; worker conditional document transitions. |
| Cards | `c:{deck}:{card}` | Job/document/deck, source and normalized card hashes, provenance/coordinates, review/import state, optional result reference and acknowledged import UUID. Point get. This entity describes generated **notes**, not an assumption that each note renders one Anki card. |
| SourceHash lookup | `s:{deck}:{sourceHash}:{compatibilityHash}` | Only source/compatibility hashes plus keys/kind; written with an acknowledged card import. Point lookup for deck-associated imported-source identity. |
| CardHash lookup | `h:{deck}:{cardHash}` | Only card hash/import UUID plus keys/kind; written atomically with card acknowledgement. Point lookup for imported-note identity. |

SHA-256 fields accept exactly 64 lowercase hexadecimal characters, supplied by
the assigned hash implementations. Compatibility hashes must eventually include
audience, relevant settings and pipeline versions (#19); this schema does not
calculate or decide that fingerprint. The SourceHash index is **not a successful
result cache** or an in-flight generation reservation. Changed compatibility
hashes miss, and pending/failed documents do not acquire permanent dedupe rows.
No semantic duplicate logic, quota reservation or exactly-once AI claim is made.

Queries use partition equality and lexicographic row-prefix ranges, with SDK
continuation paging. A retention sweep scans **one named user's partition**;
it does not discover all users or scan the whole account. The small target user
population makes a user partition acceptable; transactions serialize concurrent
deck mutations, so this is not a high-throughput design.

## Metadata and reference policy

The public methods accept typed, bounded properties, not arbitrary dictionaries,
study text or generated payloads. Store no file/deck display names, tags,
subject/chapter text, extracted sections, prompts, answers, notes, SAS URLs,
credentials or free-form error details. Subject/chapter are optional opaque
application IDs, not personal labels. Version labels must come from trusted
deployment configuration; provenance locations are numeric, not copied source
text. Usage holds nonnegative bounded integers for tokens/pages/proposed notes,
imported notes/rendered cards/duplicate skips/attempts/duration. It is not an
Azure billing total.

An artifact reference contains only an artifact UUID, class and UTC expiry.
Its full locator is resolved by #18 from **this authenticated user's partition,
deck UUID and job UUID**, plus artifact class/UUID, never an arbitrary URL.
Proposed private Blob naming contract:
`{userPartition}/{deckUUID}/{jobUUID}/{artifactClass}/{artifactUUID}`.
An artifact reference is **not access authorization**, proof of existence or
permission to retain bytes. Reference expiry is at most 24h for originals and
extraction intermediates, seven days for results/review images, and never beyond
the parent job's operational expiry. #18 must also delete originals/intermediates
on processing completion and imported payloads/media within 24h of Anki commit.
This library does not perform those Blob operations.

Operational `ExpiresAt` is fixed at initial job creation + 30 days, not extended
by transitions, claims, retries or child creation. Deck descriptive metadata has
its own creation + 30-day cutoff. Expired operational entities are unavailable
at the exact cutoff even before a sweep; expired artifact fields are omitted
from repository reads. Child reads also reject a missing/deleted/expired job.
`purge_expired()` conditionally deletes expired operational rows and reduces
expired Decks metadata to the minimal mapping guard. It preserves only SourceHash
and CardHash identities while that mapping exists. No durable document ID,
provenance, usage, timestamp or result reference is present in those indexes.

Azure Tables has **no TTL or server-side time predicate for a transaction**.
Logical denial is implemented, but a library cannot guarantee physical removal
at a wall-clock deadline without an operational caller. Parent integration must
provide a bounded, monitored user inventory/sweeper and deletion recovery, with
an earlier physical cleanup target and outage handling to stay within 30 days.
No timer, service, lifecycle policy or account has been activated here.
**Physical retention compliance is an integration/release blocker**, not a
claim that setting an expiry property deletes Azure records.

## Conditional state and worker ownership

All mutations are create-only or concrete-ETag replacements/deletes. No upsert,
wildcard ETag or cross-table transaction is used. A batch has at most 100 distinct
entities and one partition. Deck cleanup uses 99 children plus the guard per
batch. Guard conflicts and service outages propagate; callers must reread/retry
deliberately, never convert them to successful completion.

Jobs progress queued -> extracting -> generating -> ready_for_review ->
completed; completed is authenticated acknowledgement of **Anki commit**, not
merely a ready result. Active processing states may fail or be deleted; failed
and completed jobs are not silently resurrected. Deletion invalidates ownership.
A ready job requires an opaque result reference. Worker claims conditionally
install a random lease token for at most five minutes and no later than job
expiry. Transitions and document/card creation require current job ETag/token
and a locally unexpired lease. Reclaiming after lease expiry advances the job
and deck fences; stale tokens/ETags cannot publish after that reclaim.

The time check and Azure write are **not a server-atomic clock check**: a write
validated before lease/metadata expiry may arrive afterward if no competing
fence advances. Expired rows are still unreadable and cannot be reclaimed.
Integrating workers must bound operation deadlines, checkpoint/recheck before
external work and publication, and recover expiry/deletion. ETags prevent stale
publication across a committed reclaim/deletion, not exactly-once external calls
or an exact wall-clock write barrier.

Documents have conditional lifecycle transitions; Cards are proposed review
records until `record_import()` is called after Anki commit. Acknowledgement
conditionally replaces the card and creates its unique imported hash row in
the same fenced transaction, optionally creating the immutable source-hash row.
A conflicting hash never partially marks the second card imported. A repeated
acknowledgement can conflict; the future caller must inspect the persisted
import UUID to decide retry success (#24), not blindly retry insertion.
Acknowledgement may arrive after payload expiry but before operational expiry
because the Anki commit may already have succeeded. It cannot revive payloads.

## Deletion boundary proposed for #18

1. `begin_deck_deletion()` CAS-replaces the mapping with a minimal `deleting`
   guard. From that commit onward, new jobs, workers, imported hash writes and
   all user reads are rejected. Every concurrent child-write batch either
   commits before deletion or fails its guard ETag atomically.
2. **#18 must drain/revoke outstanding Blob write authority and remove all
   temporary artifacts before final Table cleanup.** Use deterministic
   user/deck prefixes to recover even after operational rows expire. The deleting
   mapping remains until this external drain succeeds; retention sweeping can
   still remove expired operational rows without reopening it.
3. Only after external cleanup, call `finish_deck_deletion()` to conditionally
   remove all five child prefixes and finally the mapping. Hash/import identities
   are physically gone when the mapping is gone. Partial failures preserve the
   deleting guard and propagate. Serial retries are idempotent; concurrent
   deleters may conflict and must reread/retry. Do not finalize on a failed drain.

**Unresolved cross-service contract:** a Table check immediately before a Blob
PUT is insufficient. A deleted job/deck can race a previously authorized upload
or already in-flight worker PUT. #18 must define a bounded write-authority
drain/expiry/revocation protocol, plus cleanup of writes that raced deletion;
only its verified cleanup may call the finalizer. Existing SAS access cannot
be magically revoked by a Table ETag. There is no Table+Blob transaction, and
this implementation intentionally does not invent Blob locks, tombstone TTLs
or claim that lifecycle deletion is an exact guarantee. Acceptance of the
physical layout, locator and drain protocol belongs to parent/lead before #18.

## Configuration and offline verification

The parent-integrated backend manifest includes the scoped storage dependencies.
Run the complete backend suite from its Functions module root:

```sh
cd backend
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The Functions app runs with `backend/` as its module root:
the library imports `auth.Principal`, exactly as the accepted foundation does.
Do not independently import the same file as `backend.auth` and create a second
class identity. No root HTTP/auth/manifest changes are made in this scoped issue.

`AzureTable.connect(endpoint, table_name)` uses `DefaultAzureCredential`;
an explicit `TokenCredential` is also supported. The endpoint must be
credential-free HTTPS with no query, userinfo or path. Select managed identity
in Azure and least-privilege **Storage Table Data Contributor** for the existing
table. No connection string, SAS, keys, provisioning or startup network probe
is required. Failures are surfaced at actual operations, including a missing
physical table (not treated as an absent user mapping). Do not log SDK exception
details or enable payload-level HTTP logging.

Behavior tests exercise isolation, hashes, ETags, races, import rollback,
retention boundaries, resumable multi-batch deletion and propagated outages
using an explicitly labelled atomic test double. Additional tests run the real
SDK against an offline HTTP transport, checking request serialization, concrete
`If-Match`, replace-vs-merge, query parameters, continuation pages, response ETags
and service 404/412/503 errors. These are **not Azure/emulator integration tests**.
No Azurite/Table emulator, Functions host, managed identity authorization,
live Azure batch/retention/deletion smoke or deployment has been verified.
