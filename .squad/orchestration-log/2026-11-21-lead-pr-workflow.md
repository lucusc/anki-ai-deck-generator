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

Bootstrap result: https://github.com/lucusc/anki-ai-deck-generator/pull/49
merged as `22258947c0fb0e6ed98b2866b94511492db6cbee`. Active children received
confirmation to sync and open issue-scoped PRs. Parent now synchronizes only
its feature checkout with merged remote main; no main-checkout writes.

PR #50 result: https://github.com/lucusc/anki-ai-deck-generator/pull/50
reviewed and verified at `fcd507d7a83651890397eb87e5114d061d8cd25e`, merged as
`04e139ab4814fe30242da616c39d5a3c9e559944`. 54 add-on and 100 backend tests
passed. #4 was accidentally auto-closed by negated closing wording, then
reopened because job/review integration remains unmet. Closing-reference
inspection is now a mandatory pre-merge guard.

PR #52 result: https://github.com/lucusc/anki-ai-deck-generator/pull/52
merged as `6ac766908daf0a6b5b85ac19d0fb63548b6df4fb` after synchronized-head
review and 70 add-on/100 backend tests. No closing references.

PR #53 result: https://github.com/lucusc/anki-ai-deck-generator/pull/53
merged as `4c08838f5e3f529484f610eada241fca88fa8145` after parser/license review
and a disposable-checkout run of 148 backend tests (six Linux-only skips on
macOS); child Linux evidence is distinct. No closing references.
