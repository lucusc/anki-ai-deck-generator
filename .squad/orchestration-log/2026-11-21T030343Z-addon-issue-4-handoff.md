# Issue #4 audience selector handoff

| Field | Evidence |
| --- | --- |
| Accountable member | addon |
| Child session | `0666d3c9-abeb-46d7-a87a-ae473ba07d5e` |
| Branch | `lucusc-audience-selector` |
| TEAM_ROOT / WORKTREE_PATH | This child's checkout; STATE_BACKEND=local |
| Ownership record | `2026-11-21T030500Z-addon-issue-4.md` |
| Accepted starting base | `fa76f4ec7ab8980ec15bdd826ec6826dd6a9f989` |
| Identity integration | `53116c8` cherry-picked as `047a559` before edits |
| Feature commit | `2ec9b52c21d6fb8661f4ee58a37a46a75331c3df` |
| Main bootstrap incorporated | `22258947c0fb0e6ed98b2866b94511492db6cbee` |
| Main merge / PR creation head | `61dacb4f56d7d70a788ea4050704c2c48412e4d6` |
| Pull request | [#50](https://github.com/lucusc/anki-ai-deck-generator/pull/50), base `main`, opened with requested `gh` workflow |
| State / outcome | Ready for parent review; full job/review acceptance and manual smoke pending |

This handoff is a separate documentation commit atop the PR creation head.
Its final commit/head SHA is returned in the coordinating report after push.
No issue closing reference is used. Parent reviews and merges serially.

## Changed paths

- `addon/models/audience.py`
- `addon/ui/audience.py`
- `addon/ui/signin.py` (audience-only wiring)
- `addon/ui/bootstrap.py` (audience-only profile lifetime)
- `addon/tests/test_audience.py`
- `addon/tests/test_load.py` (audience UI/package cases and combo data double)
- `backend/contracts/audience.py`
- `backend/contracts/__init__.py`
- `backend/tests/test_audience.py`
- `docs/audience-settings.md`
- `.squad/agents/addon/history.md`
- `.squad/decisions/inbox/addon-4-audience-settings.md`
- This unique handoff

No auth, worker, storage/retention, note mapping, root manifest or parent-owned
canonical state edits are present in the PR delta.

## Acceptance evidence

All five exact product options/wire strings are implemented. The modeless
selector starts unselected, displays the captured product label, preserves the
deck selection and resets on profile close. Closing/reopening within a profile
retains the explicit choice. Busy/close controls follow existing auth/deck
lifecycle without new network or collection work.

Frozen client/server AudienceSettings snapshots serialize the required
`audience` and detach from mutable input/output mappings and later UI choices.
An invalid new choice clears live selection, never reuses a previous audience.
Missing selection/closed capture fail explicitly. The server validator rejects
missing/unknown/case/whitespace/label/non-string values rather than substituting.
Fixed labels/errors and redacted representations avoid study-content logging.

After main bootstrap integration:

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s addon/tests -q`:
  **54 passed**, CPython 3.14.0.
- `cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest`:
  **100 passed**, CPython 3.13.9, including 23 server audience cases.
- Packaged actual-builder/extracted-artifact UI tests use Anki 25.09 and
  26.09.4 Qt6 API doubles, including no default and selected product labels.
- Client/server golden-wire, serialization, error and label parity passes.
- Mutated real source copies turn focused tests red for missing/invalid
  fallback, mutable snapshots and automatic first-option selection.
- `git diff --check origin/main...HEAD` passed before PR creation.

Backend test dependencies were missing, so restored the existing pinned
requirements into this checkout's ignored `backend/.venv`. No manifest changes,
credentials, private fixtures, paid calls or services were introduced.

## Contracts and remaining integration gates

The accepted field and wire values are unchanged. Proposed reusable API:
`AudienceSelector.capture_settings()`, frozen `AudienceSettings.to_mapping()`
and `.review_label`, and server `contracts.validate_audience_settings(settings)`.
The projection retains only audience; it is not the full future job schema.
Independent distributable client/server modules are protected by parity tests.

#7 must call the validator on parsed request settings before accepting,
persisting or enqueuing work, and return content-free 400 on missing/invalid
audience. #8 must validate persisted settings and preserve the accepted
audience in immutable private results. #5 must reconstruct/display that
accepted snapshot, not the current combo or a model-selected audience.
#19/#20 compatibility identity must include audience/settings/pipeline versions.
OAuth/API token audience remains separate; auth, profile lifetime, ownership,
atomic quotas and expiry are not satisfied by a settings snapshot.

**No actual job/review HTTP boundary or screen is implemented**, and no existing
handler calls the validator. Explicit reusable serialization/label contracts
and the current UI summary do not prove end-to-end #4 job/review acceptance.
Actual Anki/Qt/OS-store/provider, Azure and end-to-end smoke remain unperformed.
The detailed future boundary/manual matrix is in `docs/audience-settings.md`.
Do not close #4 merely because this useful slice merges. Stop after #4.
