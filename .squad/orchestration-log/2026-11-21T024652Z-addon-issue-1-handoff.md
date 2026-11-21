# Issue #1 addon committed handoff

| Field | Value |
| --- | --- |
| Accountable member/session | addon / 0d5353d4-095a-47d1-a62b-2c0d3193bb68 |
| Parent/session | Project implementation / 64c49e88-ac74-456c-8ad0-69cfa79ae399 |
| Canonical assignment | 2026-11-21T024000Z-addon-issue-1.md |
| Final branch | lucusc-anki-addon-foundation |
| TEAM_ROOT / WORKTREE_PATH | This child's checkout; STATE_BACKEND=local |
| Base/prerequisites | 69e19f5692438c132b7c06aa3cdd4bf304a89608; no application prerequisites |
| Ownership identity integration | c215bef0c5f2f2a865e91dc4bd31334b92f70ae1 cherry-picked as b2dcb85 before edits |
| Implementation commit | a4c75cd8587d33d0aaad8878bc4d23736cc1f48a |
| State/outcome | Handoff for review; manual release evidence outstanding, not issue-complete |

Parent already owns the original c215bef identity change; integrate the
implementation commit and this handoff-log commit, not the duplicate b2dcb85
identity cherry-pick. No GitHub issue state/comment/label, PR, deployment,
watcher, paid service or sibling issue was changed or activated.

## Acceptance coverage

| Live #1 criterion | Implementation and evidence |
| --- | --- |
| Loads on documented Anki versions and Tools entry | Targets 25.09 and 26.09.4 Qt6; exact unsupported-version gate. Inspected upstream menu/QueryOp/profile APIs and packaged-load API-double tests for both targets. **Actual desktop load/restart not performed.** |
| UI/services/models/tests and safe startup logging | Separate packages, one modeless sign-in dialog, fixed content-free events/errors, sanitized startup/config/background failures; tests for duplicate loads, main-thread updates, profile cancellation and late callbacks. |
| Smoke test, contributor setup, no backend secrets | Local builder, packaged-entry smoke, contributor/install/manual matrix in docs/addon-development.md. Blank public-only config; no dependency bundle or backend keys. |
| Public-client browser OAuth code + PKCE | Fresh S256 verifier/state, exact issuer HTTPS discovery, validated bounded loopback response, public client/scopes/audience, no client secret. Real synthetic browser-to-listener-to-code-exchange test; invalid state/issuer/duplicate/error responses fail. |
| Refresh only in protected OS store | Explicit native Mac Keychain, Windows Credential Manager, Linux Secret Service; no file fallback. Protected write must succeed before session acceptance; expiry/rotation, denial cleanup, local sign-out and cancellation tested. **Native OS store round trips remain unverified.** |
| Deployment-controlled identity choice | OIDC/native loopback/S256/refresh requirements and example public config documented. Parent-accepted #6 RS256 issuer/audience/JWKS boundary incorporated as deployment guidance only. **Real provider/API smoke not performed.** |

No upload/job payload, deck/audience workflow, note mapper or collection mutation
was invented. This foundation is not the document-generation application.

## Verification commands and results

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s addon/tests -v`:
  **31 tests passed** on macOS/Python 3.14.0. Includes three isolated real-source
  mutation checks that confirm the protected-write, S256 and non-collection
  worker-dispatch assertions turn red. Includes real local HTTP callback
  requests, not a live external provider.
- `git diff --check` and staged `git diff --cached --check`: passed.
- `python3 addon/tools/build.py <session-files>/anki-addon-foundation.ankiaddon`:
  built local artifact; 14 archive files, 12 Python sources compiled with
  `compile(...)`, no tests/tooling/caches included.
- Artifact SHA-256:
  `eb6aa74c49c75d45f78a0df1bbc7b10b05b8ddbc932979f71dfd094eb5f09d10`.
- Upstream `gh api repos/ankitects/anki/releases` plus public source reads:
  26.09.4 stable and 26.11b1 beta observed. Menu, QueryOp/task manager and
  no-argument profile_will_close/main_window_did_init hook signatures checked
  in both selected stable tags.
- macOS CoreFoundation bindings, query object construction and synthetic
  CFData round trip passed without reading/writing the user's Keychain.

## Changed paths

Implementation:

```text
addon/__init__.py
addon/config.json
addon/manifest.json
addon/models/__init__.py
addon/models/auth.py
addon/services/__init__.py
addon/services/callback.py
addon/services/credentials.py
addon/services/http.py
addon/services/oauth.py
addon/services/privacy.py
addon/ui/__init__.py
addon/ui/bootstrap.py
addon/ui/signin.py
addon/tests/support.py
addon/tests/test_auth.py
addon/tests/test_contract_mutations.py
addon/tests/test_load.py
addon/tests/test_transport_and_stores.py
addon/tools/build.py
docs/addon-development.md
.squad/agents/addon/history.md
.squad/decisions/inbox/addon-1-foundation-auth-targets.md
```

This uniquely named orchestration handoff is the only additional written path.
Root README/tooling/shared decisions/backlog, backend files and other histories
were not edited.

## Proposals and release blockers

Parent should review/consolidate `addon-1-foundation-auth-targets.md`, including
desktop targets, OIDC-discoverable native-client requirements, deployment/profile
credential isolation and the Windows 2560-byte credential limit. Link
`docs/addon-development.md` from root README and describe the newly implemented
foundation without claiming upload/generation/review/import readiness.

No real Anki/Qt desktop was launched. macOS Keychain store/read/delete and
Windows/Linux protected-store round trips, cancellation under OS policy prompts,
both target versions on each platform, approved-account provider registration,
real PKCE consent/refresh/revocation and deployed API issuer/RS256/audience
verification remain the explicit manual smoke matrix. Native macOS/Windows
store calls can wait on OS authorization/policy even after dialog cancellation.
Tests do not certify these missing environments; do not close #1 or declare V1
complete on this handoff alone.
