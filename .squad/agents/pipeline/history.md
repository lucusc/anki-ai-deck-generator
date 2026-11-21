# pipeline — History

## Core Context

- **Role:** Extraction / Generation
- **Joined:** 2026-11-21

## Learnings

<!-- Append new learnings below -->

### 2026-11-21 - Issue #9 PDF extraction handoff

- Assigned worktree/session `98b8c5f4-5b32-4a3a-84dc-4ba470a7be4f`, final branch
  `lucusc-pdf-extraction`; own checkout is TEAM_ROOT, STATE_BACKEND=local.
  Read live #9/#6, all current docs and canonical local Squad state. #6 prerequisite
  is integrated, but real host/cloud verification remains a release gate.
- Selected pypdf 7.1.1 (BSD-3-Clause) after reviewing PyMuPDF AGPL/commercial
  licensing; recorded the local PDF contract/units in `pipeline-9-pdf-extraction`
  inbox. No worker, auth, root manifest, storage, OCR or generation integration.
- Native eligibility is per nonblank page, not a document average. Scanned,
  short-caption and vector-only pages must remain explicit insufficiency;
  painted image resources are distinguished from unused resource dictionaries.
- pypdf strict mode can still warn and substitute missing font resources.
  Warning detection must reject the complete result without retaining diagnostics.
  Disable optional external image decoders so descendants/temp files do not
  escape the native-text resource boundary.
- pypdf constructor verifies empty passwords by default. The pinned initialization
  hook aborts encrypted inputs before crypto/page access; genuine RC4/AES and
  provider-free AES fixtures protect this private-hook dependency.
- Linux CPython 3.13.18: 52 passed, 1 platform-specific skip. macOS CPython 3.13.9:
  48 passed, 5 Linux-only skips. Actual parser CPU, wall, memory, native-stream
  expansion and precise thresholds exercised; 10 weakened copies rejected.
  Shared macOS/Linux bytecode caches initially conflicted; final runs and parser
  child use `-B`, with read-only Linux mounts and temporary cache paths.
- Real Functions subprocess/OS-limit availability, concurrent-instance headroom
  and representative document fidelity/performance are pending, not inferred
  from local container tests.

### 2026-11-21 - User-directed #9 GitHub PR integration

- Coordinator confirmed bootstrap PR #49 merged at `2225894`; merged that
  `origin/main` ancestry into this branch and kept main's canonical #21 backlog
  status rather than resurrecting the stale child assignment.
- Explicit scope extension covers backend root dependency/discovery tooling.
  Included extraction requirements and tests without changing foundation/auth/
  worker or storage behavior. Current tests/docs use `extraction` from the
  deployed backend root, not a duplicate `backend.extraction` module identity.
- Isolated child adds only the fixed Functions-vendored dependency directory
  after OS limits; a real-parser clean-interpreter fixture proves packaged
  dependency discovery without inheriting worker Python paths or credentials.
- Default backend-root suite: Linux CPython 3.13.18 **130 passed, 1 skipped**;
  macOS CPython 3.13.9 **125 passed, 6 skipped**. All ten original critical
  mutations remain rejected. GitHub PR uses a non-closing #9 reference;
  parent reviews/merges serially. Real host/Azure/concurrency/fidelity gates
  remain explicitly unverified.

- Opened https://github.com/lucusc/anki-ai-deck-generator/pull/53 after merging
  reviewed `main` through PR #50 (`04e139a`). The live PR has no closing issue
  references. Final default backend tests: Linux **153 passed / 1 skipped**,
  macOS **148 passed / 6 skipped**. Handoff now includes PR-based integration
  evidence; parent reviews/merges this issue-only delta.
