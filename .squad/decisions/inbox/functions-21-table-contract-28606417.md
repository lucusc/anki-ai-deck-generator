### 2026-11-21: #21 Table layout and external deletion boundary proposal

**By:** functions, child `28606417-5782-4a37-a98b-72a5a835744a`.

**What:** Propose one physical Azure Storage Table (`Metadata` is an example),
with logical Documents/Cards/Decks/Jobs and SourceHash/CardHash lookup entities.
Partition by `u` + SHA-256 of canonical JSON
`["anki-tables-v1", validatedIssuer, validatedSubject]`. Use the existing
`backend/auth.py` Principal class under the foundation's `auth` import identity.
Deck/job/document/card IDs are server-generated UUIDs; never reuse removed
mapping UUIDs. Rows use `d:{deck}`, `j:{deck}:{job}`, `o:{deck}:{document}`,
`c:{deck}:{card}`, `s:{deck}:{sourceHash}:{compatibilityHash}` and
`h:{deck}:{cardHash}`. See `docs/table-storage.md` for properties/access patterns.

**Why:** A concrete-ETag replacement of the Decks guard participates in every
child mutation's same-table/same-user-partition transaction. Separate physical
tables cannot atomically fence deck deletion against those writes. No
cross-table or Table+Blob transaction is asserted. This physical-layout
refinement needs parent/lead acceptance before #18 depends on it.

**Retention:** Job metadata expires at creation + 30 days; document/card expiry
cannot extend their parent's deadline. Deck descriptive metadata becomes only
the mapping guard at 30 days. Reads deny expired operational rows and omit
expired references; `purge_expired()` physically deletes operational rows and
compacts Decks. Persistent imported-source indexes contain only source and
compatibility hashes; imported-card indexes only card hash/import UUID, keys
and kind. These are removed before the deck mapping is removed. They are not
an in-flight reservation, compatible result cache or semantic duplicate check.

**Exact #18 proposal / blocker:** Resolve private artifact locators as
`{userPartition}/{deckUUID}/{jobUUID}/{artifactClass}/{artifactUUID}`.
References hold only class/UUID/expiry, never SAS URLs or content.
First CAS the deck guard to `deleting`; then #18 must drain/revoke outstanding
write authority and delete all artifacts under that user/deck prefix; only
after verified external cleanup call the Table finalizer. Keep the deleting
mapping during retries, allowing operational expiry sweeping independently.
Previously issued SAS grants and in-flight Blob PUTs can outlive a Table check.
The concrete bounded drain/revocation/late-write-cleanup protocol remains
**unresolved and must be accepted before cross-domain deletion is complete**.
Do not silently infer that Table ETags revoke Blob grants.

**Operational blocker:** Tables has no TTL/server-clock transaction predicate.
A monitored user inventory/sweeper, earlier cleanup target and outage recovery
must be integrated to prove the physical 30-day maximum. No schedule/service
was activated. Local lease/expiry checks cannot atomically constrain delayed
Azure arrival times; ETags fence committed deletion/reclaim, and logical reads
deny expired records. Runtime retention and live Azure authorization/batch
verification remain release gates.

**Scope:** No Blob operations, quota/upload/job APIs, document/card hashing,
semantic duplicate processing, root manifests/auth/HTTP edits, deployment,
GitHub writes or nested agents. Parent must reconcile scoped SDK requirements.
