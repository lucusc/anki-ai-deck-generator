# Issue #18 handoff — private temporary Blob storage

**Owner:** functions  
**Session:** `85ee0d0b-3280-4230-b3a1-b07e207c2535`  
**Branch:** `lucusc-blob-storage-retention`  
**Assignment:** `2026-11-21T030000Z-functions-issue-18.md`  
**PR:** https://github.com/lucusc/anki-ai-deck-generator/pull/55  
**Outcome:** Implementation ready for review; full acceptance remains gated.

## Commits and reconciliation

- Required ancestor: `fef3f012a8c075c82c35aa48e462b3409d2483ac`.
- Parent identity/accepted contracts `fa76f4ec7ab8980ec15bdd826ec6826dd6a9f989`
  cherry-picked before edits as `2ab351f`.
- Implementation: `7409b9fd91ddd4dea90246f400238b545dd6a7a6`.
- Canonical main integration: `77312394f45c3158013e9939f00ecfe42f81ec5d`;
  resolved the two stale add-on assignment rows to exact main state.
- Latest pre-PR main refresh:
  `01478676fe24fee6b0a2b15dcf35e039cdbc328d`, incorporating main
  `da500a7015307bfa24e88ae080fc1d31e0672c5d`.
- This handoff follows that verified tip. Its exact final SHA is returned with
  the parent report/PR head; no self-referential commit SHA is fabricated.

PR targets main, is open/non-draft, and live `closingIssuesReferences` was
verified empty. The user-directed GitHub PR workflow superseded the original
local-only handoff; no merge, issue closure, label or unattended automation was
performed by this child.

## Scope and paths

- `backend/storage/blob.py`: real Blob/ARM SDK adapter, private policy,
  zero-byte initialization, infinite lease, single conditional PUT, bounded
  reads, read-only user-delegation SAS, lease deletion and retained-copy check.
- `backend/storage/artifacts.py`: authenticated derived namespace, fenced
  inventory, immutable publication, effective expiry, deletion and bounded
  processing/import/deck cleanup.
- `backend/storage/retention.py`: complete deployment-controlled 1-5-user
  inventory, ten-row pages, durable cursors, one-hour cleanup lead,
  180-second work budget, overdue-cycle/failure reporting.
- `backend/storage/azure.py`, `repository.py`, `requirements.txt`: bounded
  production Table paging, retention timestamps/physical purge/finalization
  guard, scoped Blob/management SDK dependencies.
- `backend/storage/tests/test_artifacts.py`, `test_blob_sdk.py`,
  `test_azure.py`: behavior, concurrency/outage recovery, production transport
  serialization and source mutations; the shared HTTP response double now
  models case-insensitive headers and SDK streaming responses.
- `backend/function_app.py`, `backend/local.settings.json.example`,
  `backend/tests/test_foundation.py`: retention-only monitored timer/binding,
  inert settings template and regression coverage. Health/auth/generation
  behavior is preserved.
- `docs/blob-storage.md`, `docs/table-storage.md`,
  `docs/backend-development.md`: precise contract, integration appendix and
  explicit deployment/retention evidence gaps.
- `.squad/agents/functions/history.md`,
  `.squad/decisions/inbox/functions-18-leased-temporary-artifacts-85ee0d0b.md`
  and this unique handoff.

The final PR diff contains only these assigned paths. Root manifests,
README/shared decisions/backlog, other member code and ownership updates came
from main, not this issue's implementation delta.

## Acceptance evidence

On macOS/CPython **3.13.9**, `cd backend &&
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -o addopts='' -q` at the
latest pre-PR tip: **192 passed, 6 skipped** in 2.58 seconds. The six skips are
existing Linux-only PDF process/resource checks. Before main integration,
**121 storage/foundation cases** passed. Syntax compilation and diff whitespace
checks passed. No temporary generated artifacts remain in the worktree.

Synthetic tests cover all four artifact classes; exact issuer/subject isolation;
24h/seven-day/committed-acknowledgement cutoffs; failed-file physical removal;
immediate originals/intermediates cleanup; immutable writes; expired/stale
workers; PUTs on either side of deletion; late initialization; deletion outage,
lost Table acknowledgement and retry; bounded multi-page drain; pending
initialization that does not prevent other expiry work; physical thirty-day
metadata purge and monitored continuation.

Real Azure SDKs run against socket-free transports: exact conditional request
headers, zero-byte create, infinite lease, single-PUT payload, bounded reads,
lease-based delete with snapshots included, user-delegation SAS read-only scope/
expiry, actual ARM policy deserialization, private container, version inventory,
SDK page continuation and 404/412/503 propagation. A configured timer-path test
executes the real Table/Blob/ARM SDK adapters with synthetic HTTP transports,
not a fake-only production substitute. Source mutations removing physical
delete, exact expiry or the lease header break the relevant assertions.

## Supported fence and unresolved gates

Do not issue write SAS. Content writes require an acknowledged pre-existing
leased placeholder and concrete If-Match. A winning earlier PUT is removed by
lease-based deletion; a later leased/conditional PUT cannot create a missing
Blob. Only after Blob deletion succeeds is its inventory removed; Table deck
finalization refuses remaining artifact rows. Failed cleanup retains the guard.
This is not a Table+Blob transaction or an elapsed-time writer drain.

An ambiguous empty create/lease call, initializer death or lost initialization
acknowledgement has no automatic settlement API. It remains a tracked safety
blocker, requires demonstrated request settlement/operator reconciliation, and
can outlast a retention deadline during an unresolved outage. HEAD or a nominal
thirty-second timeout is not proof; Azure permits ten minutes per MiB for PUT.
The implementation does not claim unconditional exact physical compliance.

Actual live Azure streaming-PUT/deletion semantics, managed identity/data plus
management-read RBAC, no-copy policy, read SAS expiry, host timer execution,
complete inventory, external alerts and cleanup/recovery within the maxima
remain unverified. The timer is disabled in the local example and was never
started. Completion/import callbacks must be wired by their assigned consumers;
partial-import media association is not inferred. Thus neither full #18 nor
full #21 completion is claimed and dependent dispatch still needs parent review.

No local original or imported Anki media is deleted. No upload/job HTTP endpoint,
quota/hash/generation work, runtime agents, nested sessions, deployment,
service/watcher, paid call or real Anki/provider/cloud run occurred.

GitHub's push response separately reported pre-existing default-branch dependency
alerts (33 total, including critical/high). This is an uninvestigated forge
report, not a security audit or permission to modify unrelated dependencies;
parent should account for it in release readiness.
