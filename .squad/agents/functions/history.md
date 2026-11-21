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
