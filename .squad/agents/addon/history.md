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

### 2026-11-21 — Issue #4 audience selector

- Own checkout/TEAM_ROOT with STATE_BACKEND=local; dispatch identity 53116c8
  integrated as 047a559 before edits. Branch: lucusc-audience-selector.
- Added all five exact accepted product options to the existing single
  modeless Tools workflow, with no initial default, explicit read-only label,
  profile-local reopen state and profile-close reset. Audience changes never
  touch destination selection, credentials, collection or network.
- Frozen AudienceSettings is an audience-only projection, not the full future
  job schema. Capture detaches from mutable mappings and later combo choices.
  Invalid reselection clears the live choice instead of reusing old settings.
  Server validator rejects missing/unknown/non-string values with fixed errors.
- Client/server contracts are independent distributable modules with tested
  golden/round-trip/error parity; never import the add-on entry point in backend.
  OAuth/API token audience remains separate from study audience settings.
- 54 add-on and 100 backend/storage regressions passed, including packaged
  Anki target doubles and source mutations for defaults/validation/immutability.
  Actual Anki/Qt/provider and job/review endpoint integration remain open.
- docs/audience-settings.md and addon-4-audience-settings.md describe the exact
  #7 validator caller, #8 persisted snapshot and #5 review label obligations.
  Parent owns full schema/state acceptance and serial PR review/merge.
