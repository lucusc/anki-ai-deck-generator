# functions — History

## Core Context

- **Role:** Backend Developer
- **Joined:** 2026-11-21

## Learnings

<!-- Append new learnings below -->

### 2026-11-21 — Issue #6 Functions foundation

- Accountable child: `7cff93fc-c604-45b1-a67d-7fdb0ec98b89`; own worktree
  `TEAM_ROOT`, `STATE_BACKEND=local`. Integrated parent ownership identity commit
  `c215bef0c5f2f2a865e91dc4bd31334b92f70ae1` as local `6d480d4` before edits.
  Final app-managed branch: `lucusc-azure-functions-foundation`.
- Chose Functions v4/Python v2 model, Python 3.13 and Linux Flex Consumption FC1.
  Microsoft Learn explicitly documents East Asia/Python 3.13/FC1 compatibility;
  production region/data residency and subscription availability remain review
  gates. Zero always-ready instances and a five-minute worker execution budget.
- Private route example validates RS256 issuer, API audience, signature,
  expiration, issued-at, optional not-before and nonempty subject. No trust in
  caller-supplied identity headers. Empty configuration and provider outages
  fail closed. Per-operation permissions/ownership remain dependent issue work.
- `functools.wraps` on a handler accepting an injected principal exposes the
  original two-argument signature to worker introspection. The auth wrapper must
  expose only the bound `req` argument; registration tests protect this.
- No payload contract or successful queue processing is invented. Every worker
  invocation raises content-free `ProcessingUnavailable`; host retries are
  bounded and poison messages are preserved for later recovery design.
- Validation: 34 offline tests passed on CPython 3.13.5, syntax compilation and
  whitespace checks passed. Three in-memory mutations of real source (signature
  verification disabled, auth bypassed, worker exception removed) were rejected
  by focused tests; files were unchanged and the clean suite passed again.
- Functions Core Tools and Azurite were absent; real host HTTP/queue/poison
  behavior was not smoke-tested. No Azure/real-provider smoke or subscription
  region check was performed; no deployments, paid calls or GitHub writes.

### 2026-11-21 — Issue #21 Table schema handoff

- Accountable child `28606417-5782-4a37-a98b-72a5a835744a`, own checkout as
  `TEAM_ROOT`, `STATE_BACKEND=local`; final branch `lucusc-table-storage-schema`.
  Parent identity `1c87f33` cherry-picked as `24ab170` before edits; implementation
  `d9077c62eb224d904e8703ff2a27a5c95d1a5351` follows accepted #6 base `5b771c2`.
- Logical Documents/Cards/Decks/Jobs live in one physical Table/user partition.
  Every child write includes a concrete-ETag deck guard replacement in the same
  transaction, fencing committed deletion/reclaim without inventing cross-table
  atomicity. Partition includes the exact validated issuer/subject pair; keep the
  existing Functions module-root `auth.Principal` class identity.
- Operational expiry is fixed at job creation + 30 days; children cannot extend
  it. Deck descriptive fields expire separately. Only imported-source hashes
  (including compatibility hash) and card hashes/import UUIDs persist with the
  minimal deck mapping. Result locators are opaque class/UUID/expiry, not content
  or SAS URLs. Explicit lookup identity is not a result cache or hash algorithm.
- Deck deletion first fences, then requires external Blob write-authority
  drain/cleanup, then removes Table children and mapping. Table checks do not
  revoke issued SAS or stop already in-flight PUTs. Exact #18 drain semantics and
  bounded physical retention scheduling remain parent/lead integration blockers;
  proposed contracts are in `functions-21-table-contract-28606417.md`.
- Production Azure SDK adapter is tested through a socket-free HTTP transport:
  conditional multipart batches, ETags, partitioned queries/continuations and
  404/412/503 failures. Offline atomic test double is separately labelled.
  Final suite: 43 storage + 34 existing foundation tests, 77 passed on Python
  3.13. Compile/whitespace and Functions module-root Principal checks passed.
  In-memory source mutations removing deck fencing, the exact retention cutoff
  and issuer isolation were rejected; no source files were mutated on disk.
- No emulator/real Azure Table, managed identity/RBAC, Functions host or physical
  retention/deletion service was exercised. No Blob operations, root manifests,
  HTTP/auth changes, quotas, hash algorithms, deployment, paid/GitHub writes or
  nested agents. Stop after committed handoff; parent reconciles dependencies.

### 2026-11-21 — Issue #18 temporary Blob implementation

- Accountable session `85ee0d0b-3280-4230-b3a1-b07e207c2535`; own checkout as
  TEAM_ROOT/WORKTREE_PATH with STATE_BACKEND local. Parent accepted-contract
  identity commit `fa76f4e` integrated locally as `2ab351f` before edits.
  App-managed branch is `lucusc-blob-storage-retention`.
- Keep the accepted locator and physical Table. Artifact rows and the bounded
  retention cursor contain only operational identity/fences, never study content,
  SAS or display metadata. Payloads are immutable single PUTs, at most 16 MiB;
  actual total upload/expansion quotas remain assigned to their consumers.
- Ordinary write SAS cannot be made to require application If-Match/lease
  discipline. Use only single-blob read SAS, at most five minutes; future upload
  code mediates authenticated server bytes. Missing leased blobs reject later
  leased/conditional payload PUTs; delete without a stale ETag removes earlier
  winning writes. Do not release a lease before deleting its content.
- Empty placeholder create plus infinite lease must both acknowledge before any
  content write is possible. Ambiguous initialization remains a tracked drain
  blocker; neither elapsed timeout nor a HEAD response proves request settlement.
  Azure's ten-minutes-per-MiB write exception invalidates naive thirty-second
  drain assumptions. Real streaming write/delete races remain unverified.
- Blob data-plane get_service_properties omits versioning/restore settings in the
  pinned SDK; use real ARM management policy reads and scoped management Reader
  actions, not nonexistent dictionary properties or a fake-only policy check.
  Retained versions/deleted copies are detected before base deletion; snapshot
  inclusion does not delete retained versions.
- A bounded deployment-controlled user inventory and conditional physical purge
  are wired to an inert-by-default monitored timer. Persist continuation,
  start cleanup one hour early, report overdue cycles/outages/pending drain,
  and keep failed guards. This is not unconditional physical thirty-day
  compliance through unavailable storage or an unresolved initializer.
- No nested agent/session, host, service, watcher, deployment or paid calls.
  User-directed PR reconciliation superseded the original no-PR handoff via
  the parent message; merge current origin/main before opening the issue-only
  PR, preserve canonical ownership, and use only non-closing issue references.
