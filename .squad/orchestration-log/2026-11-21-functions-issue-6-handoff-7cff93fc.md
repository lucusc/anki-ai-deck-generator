# Issue #6 Functions handoff

| Field | Evidence |
| --- | --- |
| Accountable member | functions |
| Accountable child | `7cff93fc-c604-45b1-a67d-7fdb0ec98b89` |
| Parent | `64c49e88-ac74-456c-8ad0-69cfa79ae399` |
| Assignment | `2026-11-21T024000Z-functions-issue-6.md` |
| Final branch | `lucusc-azure-functions-foundation` |
| State / outcome | Implementation committed; parent review, not release approval |
| Ownership identity | Parent `c215bef0c5f2f2a865e91dc4bd31334b92f70ae1`, integrated locally as `6d480d4` before edits |
| Implementation commit | `3ee0d680311ec52ee99f34dc1be3a192a81ac7ae` |
| Team state | Own worktree `TEAM_ROOT` / `WORKTREE_PATH`, `STATE_BACKEND=local`; canonical roster unchanged |

The parent already owns the original identity commit; integrate the feature
commit and this handoff, not the duplicate cherry-picked identity commit.
No other checkout, root tooling/README, canonical decisions/backlog, addon or
pipeline files were modified.

## Acceptance coverage

| Live #6 criterion | Implementation and evidence |
| --- | --- |
| Python Functions app and documented region/runtime-compatible Consumption plan | `backend/function_app.py`, `host.json`, pinned manifests; Functions v4/Python v2 model, Python 3.13/Linux Flex FC1/East Asia documented with current Microsoft Learn references and subscription preflight commands |
| Health endpoint and credential-free local template | `GET /api/health` serves exactly `{"status":"ok"}` with no-store; emulator-only `local.settings.json.example`; Git/publication excludes real settings and local artifacts |
| Authenticated route structure and tests | `GET /api/v1/auth-check`, reusable bearer wrapper, RS256 signature/issuer/audience/time/subject validation, no forged identity-header trust, explicit 401/503; real SDK route inventory and single-bound-argument worker signature assertions |
| Queue-worker entry point and no long HTTP generation | Internal `generation-jobs` queue binding; every invocation raises actionable `ProcessingUnavailable`, no body logging or successful acknowledgement; bounded timeout/retries; no HTTP submission/generation or fabricated job contracts |

## Commands and results

- `gh issue view 6 --repo lucusc/anki-ai-deck-generator --json title,body,url`
  and live #7/#8/#18/#21 body reads: reviewed current scope and appended
  auth/quota/retention additions; direct #6 prerequisites are none.
- Command-scoped identity cherry-pick of the parent ownership commit: succeeded
  as `6d480d4`, without changing global Git configuration.
- `cd backend && uv venv --python 3.13 .venv && uv pip install --python
  .venv/bin/python -r requirements-dev.txt`: installed declared dependencies on
  CPython 3.13.5, no cloud credentials.
- `cd backend && .venv/bin/python -m pytest`: **34 passed** after fixes; final
  repeat also **34 passed**. RSA fixtures and JWKS responses are synthetic;
  real PyJWT signature/claim/key lookup and real decorated route calls are used.
- Inline Python mutation harness loaded the real module source in memory and
  independently disabled signature verification, bypassed authentication and
  removed the unavailable-worker exception. Corresponding targeted pytest
  selections failed for all three mutants; harness succeeded. On-disk files
  were never changed and the normal suite passed again.
- `.venv/bin/python -m compileall -q auth.py function_app.py`: passed.
- `git diff --check` and staged whitespace check: passed.
- `git check-ignore local.settings.json .venv __pycache__` from `backend/`:
  all three paths ignored. Only the credential-free template is tracked.
- `command -v func` and `command -v azurite`: absent. Local host HTTP and queue
  retry/poison smoke tests were not run. No watchers/services were launched.

## Changed paths

- `backend/.gitignore`
- `backend/.funcignore`
- `backend/auth.py`
- `backend/function_app.py`
- `backend/host.json`
- `backend/local.settings.json.example`
- `backend/pyproject.toml`
- `backend/requirements.txt`
- `backend/requirements-dev.txt`
- `backend/tests/test_foundation.py`
- `docs/backend-development.md`
- `.squad/agents/functions/history.md`
- `.squad/decisions/inbox/functions-6-runtime-auth-boundary.md`
- This uniquely named handoff log.

## Proposed decisions and remaining verification

Parent review/consolidation requested for
`functions-6-runtime-auth-boundary.md`: runtime/region target, RS256 provider
configuration and `(issuer, subject)` identity, minimal route example, provisional
internal queue binding and explicit unavailable-processing behavior.
Parent-owned root change requested: README link to backend development docs.

No implementation blocker remains within the scoped foundation. Production
region/data residency and allowed users/permissions are still deployment design
decisions. Azure subscription region/runtime preflight, real identity-provider
validation, Functions host startup, HTTP smoke and queue retry/poison placement
remain **unverified**, not inferred from SDK tests. The service intentionally
cannot process jobs until the dependent pipeline issue is implemented.

#7/#8/#18/#21 storage, atomic quotas, per-operation authorization,
expiry/tombstones, retention and deletion were not implemented. Their requirements
remain binding; the auth-check route is not artifact authorization. No GitHub
state changes, PR operations, deployments, paid calls or nested agents/sessions
occurred. Stop after this committed handoff; the parent owns reconciliation.
