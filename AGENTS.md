# Contributor and Copilot Session Instructions

This repo currently contains requirements and Squad development coordination,
not a working app. Implement only the assigned issue; do not scaffold unrelated
runtime systems or interpret the backlog as permission to work on every issue.

Before work, read `README.md`, all `docs/*.md`, the live assigned issue including
appended security/retention criteria, and `.squad/team.md`, `routing.md`,
`decisions.md`, `backlog.md`, `governance.md`, plus your member charter/history.
The parent supplies ownership, accepted prerequisite evidence and exact scope.
Use your own checkout as `TEAM_ROOT` with `STATE_BACKEND=local`.

Use the same Squad roster in Copilot app children. Follow the ownership/handoff
procedure in `.squad/governance.md`; children never mutate the main checkout or
another session. Record decisions in the canonical inbox and return committed
changes and evidence to the parent for serial reconciliation.

Squad is development tooling only. Preserve the deterministic runtime pipeline
and architecture's **No agents** decision. V1 includes #1-42 and image occlusion;
#43-48 are post-V1. Respect browser OAuth/PKCE, protected refresh credentials,
per-user atomic quotas, private temporary artifacts, deletion/expiry and
content-free telemetry as summarized in `.squad/decisions.md`.

Use focused tests for introduced behavior and synthetic/openly licensed fixtures.
Keep Anki UI responsive and collection access supported; no silent success
fallbacks. Record missing real Anki/Azure verification rather than claiming it.
Never commit secrets, document contents or student information.

No unattended GitHub writes, watchers, automatic PR creation/merge, deployment,
or paid services are authorized by the Squad setup. Do not activate generated
workflow templates. Application deployment tooling belongs to its tracked issues.
