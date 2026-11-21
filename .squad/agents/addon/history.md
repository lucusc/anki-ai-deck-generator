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
