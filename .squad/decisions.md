# Squad Decisions

## Active Decisions

### 2026-11-21 — Squad is development coordination only

**Owner:** lead. Use official github/squad CLI 2.0.0, initialized with
`init --preset default --no-workflows --no-vscode-default --client copilot --state-backend local`.
No application SDK dependency is added. The architecture's **No agents** decision
remains unchanged: extraction -> chunking -> generation -> validation -> merge
is deterministic. This setup does not implement any application issue.

### 2026-11-21 — Explicit dispatch and versioned local team state

**Owner:** parent coordinator / lead. Use five specialists, canonical Squad
team/routing/decisions, offline `backlog.md` and orchestration logs. GitHub issues
remain authoritative requirements. No unattended GitHub writes, watcher,
deployment, paid service or automatic PR operation is enabled. Copilot app
children use local team copies and report updates to one coordinator; do not
share mutable files via the main checkout. See `governance.md`.

### 2026-11-21 — V1 authentication, quota and temporary-retention baseline

**Owners:** functions and addon; reviewer tester. The appended issue criteria
are binding even where the older PRD leaves defaults unresolved:

- Public-client browser OAuth authorization code with PKCE; refresh credentials
  only in the protected OS credential store. Identity provider is deployment
  configuration; no add-on API/Function/Azure/storage keys.
- Authorize every upload/job/status/result/deletion against the authenticated
  user. Atomically reserve per-user upload-byte, stored-byte and outstanding-job
  quotas across concurrent requests. Direct-upload grants cover one assigned
  blob, the required operation, and a short lifetime.
- Abandoned uploads: maximum 24h; failed-job files: 24h for retry. Delete originals
  and extraction-only intermediates on extraction/generation completion.
- Results and review images (including diagrams): at most 7 days; after Anki
  acknowledges committed import, delete backend payloads/media within 24h.
- Content-free job status/usage and telemetry: at most 30 days. Tables contain
  no document text/generated payload. Minimal dedupe hashes/import IDs live only
  while the associated deck mapping exists, and are deleted with that mapping.
- Deletion is authenticated and idempotent for every artifact class. Late or
  redelivered workers must not recreate expired/deleted artifacts. Lifecycle
  deletion is an asynchronous backstop, not an exact expiry deadline; account
  for soft-delete/version/snapshot retention and avoid unnecessary copies.
- Disclose cloud processing/expiry before upload and during review. Expired
  results require re-upload; never delete local originals or imported media.

Relevant issues: #1, #2, #5, #7, #8, #18, #21, #24, #31, #34 and #42.

### 2026-11-21 — Release and verification boundaries

**Owner:** lead; reviewer tester. #1-42 all belong to V1, including the complete
image-occlusion workflow and demonstrated Image Occlusion Enhanced path.
#43-48 remain post-V1 even when their graph prerequisites are satisfied.
Review PDF parser licensing, Functions SKU/runtime/region, identity-provider
configuration, measured limits/pricing and supported Anki versions in their
assigned issues; do not invent completed decisions or compatibility evidence.
Use synthetic/openly licensed fixtures and no private study content in commits,
logs, or telemetry. Paid OCR is explicitly enabled and bounded, never implicit.

## Governance

### 2026-11-21 — Foundation parallel-write boundaries

**Owner:** parent coordinator / lead. #1 owns `addon/` and
`docs/addon-development.md`; #6 owns `backend/` and
`docs/backend-development.md`. Each owns only its member history and uniquely
named decision/handoff records. Root README, root tooling, shared decisions and
backlog changes are reconciled by the parent, not parallel writers.

Both foundations use a deployment-configured OAuth public client and API
audience, never shared secrets. The add-on obtains access tokens through browser
authorization code with PKCE and protected refresh storage; the backend must
validate access-token issuer, signature, audience, lifetime and user identity,
or a documented trusted hosting authentication boundary. No unverified
identity headers are trusted in an exposed local endpoint. Backend contracts
are not accepted merely because a sibling proposed them. A public health route
returns only operational health, never configuration, credentials or content.
Upload/job payloads belong to dependent issues and require an accepted shared
contract before their parallel implementation.

Record proposed changes in `decisions/inbox/{member}-{slug}.md`; the parent
coordinator consolidates accepted decisions and integrates child histories/logs.
Issue acceptance criteria and explicit user scope cannot be weakened by a
generated template. Resolve disagreements before depending on a changed contract.
