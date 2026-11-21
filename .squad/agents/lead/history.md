# lead — History

## Core Context

- **Role:** lead (Coordinator / Architect; stable casting role)
- **Joined:** 2026-11-21

## Learnings

- 2026-11-21: Reviewed #3 and integrated `acf2549`/`160605a`; all 45 add-on
  tests pass. Accepted immutable numeric deck identity with explicit revalidation.
  #4 UI and #25 isolated note-mapping modules can now proceed in parallel.

- 2026-11-21: Reviewed #21 and integrated `56a2a09`/`e9791de`; 77 backend
  tests pass after aligning tests/default runner with the Functions module root.
  Accept physical single-table fencing layout, but keep physical-retention and
  Blob late-write drain gates open for #18 before dispatching dependent APIs.

- 2026-11-21: Accepted #1 implementation offline as `0c0ce0a`/`a13c5c4`;
  coordinator reran 31 add-on and 34 backend tests. Desktop, native-store and
  provider evidence remains open. Serialize #3/#4 shared UI wiring while #9
  extraction and #21 storage continue in disjoint backend scopes.

- 2026-11-21: Accepted #6 implementation as `032393e` with handoff `9f7311f`;
  reviewed authenticated route/queue boundary and reran 34 backend tests in the
  coordinator checkout. Real Functions host/cloud/provider smoke remains open.
  Release gates are not inferred from offline acceptance of the foundation.

- 2026-11-21: Read all project docs and the acceptance criteria of issues #1-48,
  including appended OAuth/PKCE, atomic-quota and temporary-retention criteria.
  Computed nine V1 dependency waves from actual Direct prerequisites; only #1
  and #6 have no prerequisites. #43-48 are held post-V1.
- Squad local state is not shared or locked across app worktrees. Parent-owned
  orchestration records and serial handoff reconciliation are required.
- Official CLI 2.0.0 refuses role changes to existing provenance IDs even with
  `cast --force`. Keep lead's registered role and cast new named specialists;
  retire unused preset identities with the official atomic casting SDK API.
