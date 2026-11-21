# User-directed PR integration

2026-11-21: User requested `gh` PRs and merges into `main` rather than local
branch aggregation. Active #9/#18/#4/#25 children received the direct App source
and must wait for bootstrap-main confirmation before syncing and opening PRs.

Bootstrap scope: official Squad integration, reviewed #1/#6/#3 foundations,
reviewed #21 schema with explicitly unresolved retention/deletion gates, root
tooling reconciliation and canonical dispatch/acceptance logs. No closing
references: actual desktop/provider/cloud and physical retention criteria
remain open. No duplicate PRs for those already accumulated feature commits.

Next state: bootstrap PR pending creation and review-gated GitHub merge.
After merge, notify active children of the real merged main commit; reconcile
future issue handoffs via GitHub PRs and preserve shared ancestry.
