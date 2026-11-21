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
