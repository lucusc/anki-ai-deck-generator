# addon — History

## Core Context

- **Role:** Python Anki Add-on
- **Joined:** 2026-11-21

## Learnings

<!-- Append new learnings below -->

### 2026-11-21 — Issue #1 foundation

- Own checkout/TEAM_ROOT with STATE_BACKEND=local; parent identity c215bef was
  integrated before edits as b2dcb85. Final branch: lucusc-anki-addon-foundation.
- Implemented dependency-free Tools/sign-in foundation, browser authorization
  code with fresh S256/state, exact-issuer discovery, bounded loopback/TLS
  transport, native protected refresh stores, memory-only access tokens,
  profile cancellation and local sign-out. No sibling issue runtime or
  backend contracts were implemented.
- Anki 25.09 and 26.09.4 expose the inspected menu, QueryOp.without_collection
  and profile lifecycle APIs. Automated packaged-load doubles are not actual
  Anki/Qt smoke evidence. OS store/provider round trips remain manual gates.
- Scope responses can omit OIDC identity scopes while retaining the requested
  API scope; refresh credentials themselves demonstrate offline issuance.
  Profile close must not re-reject a Qt dialog already scheduled for deletion,
  and cancellation during protected writes must not accept a late session.
- Native macOS CoreFoundation query/data bindings can be exercised without
  touching the user's Keychain. Linux secret-tool tokens must be stdin-only;
  Windows generic credential blobs have a 2560-byte ceiling.
- Decision proposal: addon-1-foundation-auth-targets.md. Root README linking
  and shared decision/backlog reconciliation belong to the parent.

### 2026-11-21 — Issue #3 deck selector

- Own checkout/TEAM_ROOT with STATE_BACKEND=local. Dispatch dbde7a8 integrated
  as 7d71133 before edits; branch renamed through the app to lucusc-deck-selector.
- Single modeless Tools workflow now offers explicit normal-deck selection and
  user-directed creation. Reads use QueryOp; writes use CollectionOp and the
  supported add_normal_deck_with_name result. No upload/audience/import added.
- Capture immutable numeric deck ID plus display-only name, revalidate inside
  the future collection write, and never use a renamed/reused name or Default
  fallback. Profile-local selection survives dialog reopen, not profile close.
- Name components must reject whitespace/colon edges, empty components, controls
  and quotes before Anki silently normalizes them; NFC normalization is explicit.
  Duplicate checks include filtered names even though filtered targets are excluded.
- Auth and deck operation controls gate each other; queued work checks a close
  event before collection access and callbacks ignore closed windows. An already
  running creation can commit after close and must not be silently deleted.
- Contract proposal: addon-3-stable-deck-contract.md; docs/deck-selector.md records
  API evidence and honest desktop/provider/undo gaps. Parent owns reconciliation.

### 2026-11-21 — Issue #25 note model mapper

- Own checkout/TEAM_ROOT, STATE_BACKEND=local; required parent identity integrated
  as 047a559. App-renamed branch lucusc-note-model-mapper. Per revised user PR
  workflow, merged origin/main bootstrap 2225894 before publication.
- Implementation c1ce981 defines strict schema_version=1 generated notes and
  dedicated Basic/reversed/Cloze managed models, preserving customized built-ins
  and failing on incompatible managed field/template/CSS/deck overrides.
- Sanitizer must account for Anki non-HTML syntax too: generated LaTeX/sound
  markers fail; source/provenance escape brackets/braces as well as HTML.
  Cloze accepts documented c1-c99 nonnested tokens after entity decoding.
- Return unsaved note, revalidated numeric deck identity and optional model
  changes. Creation defaults off, explicit boolean only; no insertion, flush,
  approval, dedupe lookup or acknowledgement. Identity lives in Import ID field,
  becoming durable only when later approved insertion commits it.
- 16 focused tests and all 61 add-on tests pass. Source mutations protect
  identity, attribute stripping and model customization gates. Packaging
  includes all mapper modules and excludes tests.
- docs/note-payload.md and addon-25-note-payload-v1.md are a producer contract
  proposal for parent/lead acceptance, not an implemented generation endpoint.
  Anki 25.09/26.09.4 public APIs inspected; real desktop saved rendering/browser
  views/restart/undo/persistence/Qt and backend/import integration remain open.
