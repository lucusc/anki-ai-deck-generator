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

### 2026-11-21 — Deck identity and next disjoint add-on scopes

**Owner:** parent coordinator / lead. #3 integrated as `acf2549`/`160605a`;
parent reviewed deck/API/UI behavior and reran all 45 add-on tests. Accept
immutable numeric `DeckIdentity` with profile-local selection and explicit
rename/deletion revalidation. Capture and revalidate the same ID within the
serialized collection operation immediately before later import; never resolve
by a reused name or default fallback. Filtered decks are not import targets.
Actual desktop/undo checks remain unverified.

#4 owns audience UI wiring, dedicated client models and a dedicated server
validator under `backend/contracts/`, without touching auth/retention routes.
The audience contract is required field `audience`, exact wire values
`middle_school`, `high_school`, `university`, `certification`, `professional`,
with corresponding product labels. Unknown or missing values fail validation,
not default/alias coercion. Capture immutable job/review settings so later
UI changes do not alter an accepted request's audience. Actual job/review HTTP
integration is not invented before #7/#8/#5.

#25 owns dedicated note payload/model-mapping/markup modules and tests, not
existing Tools/sign-in/deck/audience modules. It proposes the typed versioned
note contract for later backend generation; root manifests, shared docs/state
and runtime import/generation endpoints remain outside its scope.

### 2026-11-21 — Accepted Table schema with unresolved integration gates

**Owner:** parent coordinator / lead. #21 feature/handoff integrated as
`56a2a09`/`e9791de`; coordinator reran 77 backend/storage tests. Tests and the
default runner now use the deployed Functions module root, avoiding duplicate
`backend.storage`/`storage` package identities.

Accept one physical Azure Table with logical Documents/Cards/Decks/Jobs,
user partition derived from validated issuer/subject, never-reused server deck
mapping UUIDs, and a concrete-ETag deck guard in each child transaction.
Accept imported source/card hash lookup rows as minimal identity indexes,
not compatible result caches or in-flight generation reservations.
Opaque artifact locator proposal is
`{userPartition}/{deckUUID}/{jobUUID}/{artifactClass}/{artifactUUID}`.

Schema-level exact-cutoff denial and `purge_expired` are implemented, but
physical 30-day retention requires bounded monitored sweep integration.
Table fencing alone cannot revoke SAS or stop an already authorized Blob PUT.
#18 must implement and verify write-authority invalidation/drain and raced-write
cleanup before deck finalization; failed cleanup retains the deleting guard.
These remain integration blockers, not accepted guarantees. #7/#19/#23 cannot
be dispatched on a claim that #21's physical retention/deletion is complete.

#18 owns new Blob/retention modules, tests and scoped dependencies under storage,
plus directly required retention extensions to the existing repository/adapter.
It does not replace the accepted keys, auth or ETag contracts, or implement
unassigned upload/job/quota endpoints. #18 may add only retention-related timer
bindings/configuration and directly related foundation tests, preserving HTTP
and generation-worker behavior. Parent owns root manifests and shared docs.

### 2026-11-21 — Accepted #1 foundation, desktop evidence still open

**Owner:** parent coordinator / lead. Reviewed and integrated #1 as `0c0ce0a`,
handoff `a13c5c4`; coordinator reran all 31 add-on tests and 34 backend tests.
Accept Qt6 desktop 25.09 and 26.09.4 as compatibility targets, not demonstrated
real-desktop support. Actual Anki restart/Qt, native credential-store round
trips and approved-provider consent/refresh/revocation remain release gates.

Accepted public config is issuer/client_id/audience/scopes. Browser sign-in
requires exact-issuer OIDC discovery, S256 and a native-client ephemeral IPv4
loopback redirect. Refresh credentials use native protected OS stores and
profile/deployment-specific accounts; access tokens stay in memory. Windows
refresh blobs have an explicit 2560-byte limit. Provider compatibility must be
verified against the accepted RS256 API boundary before production use.

#3 owns deck models/services/widget, the existing Tools/sign-in UI wiring and
its related tests. #4 waits for that shared UI write ownership to be released;
this is serialization of files, not a new graph prerequisite.

### 2026-11-21 — Accepted #6 foundation, not production deployment

**Owner:** parent coordinator / lead. Reviewed and integrated #6 as `032393e`
and handoff `9f7311f`. Coordinator CPython 3.13 suite verifies all 34 tests.
Accept Python 3.13 / Functions v4 / Linux Flex Consumption FC1 as the foundation
target. East Asia is a documented compatible example, not approved production
data residency; subscription availability and real host/cloud/provider smoke
remain unverified release gates.

Use `backend.auth.Principal` with the validated `(issuer, subject)` identity;
fixed deployment-controlled HTTPS issuer/JWKS and API audience; RS256 bearer
validation and no caller identity-header trust. Child modules must not bypass
this authentication boundary. The provisional `generation-jobs` queue worker
deliberately fails until #8 provides actual processing; there is no accepted
job payload contract or upload API yet.

#9 owns `backend/extraction/**` and `docs/pdf-extraction.md`; #21 owns
`backend/storage/**` and `docs/table-storage.md`. Each keeps optional dependencies
within its subtree and does not change backend root entrypoints/manifests.
Parent reconciles dependency manifests and imports after reviewing the handoffs.
Implement Blob operations after the Table ownership/retention contracts are
reconciled, avoiding parallel invention of competing storage state.

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
