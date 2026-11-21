# Issue #27 independent visibility revision

| Field | Value |
|-------|-------|
| Accountable member | tester |
| Session | `0b89c5d3-85aa-4d2f-a1a9-ed9b9f6bb572` |
| Branch | `lucusc-reversed-visibility-revision` |
| TEAM_ROOT / WORKTREE_PATH | `/Users/lucuscrawford/copilot-worktrees/anki-ai-deck-generator/lucusc-curly-fishstick` |
| STATE_BACKEND | `local` |
| Model | Auto Balance |
| Direct prerequisite | #25, reviewed/merged PR #52 (`6ac7669`) |
| Revision baseline | Original issue-27 helper `6e08544a924afa1253630da4b0859184783d6298`, published on `lucusc-reversed-note-import`; contains dispatch `2807a52` |
| Write scope | `addon/services/reversed_notes.py`, `addon/tests/test_reversed_notes.py`, `docs/reversed-notes.md`, tester history, unique tester-27 inbox/handoff |
| Locked-out author | addon session `d5047891-fb6a-4a71-89da-177af022d8fb`; no revision/advice/coauthorship this cycle |
| Identity check | Revision and original session IDs differ; tester is a different canonical roster member |
| State / outcome | assigned; execution after ownership integration / pending |

Parent review reproduced four public-import failures on real core 26.9.4:
U+FE0F, U+034F, U+3164 and U+115F alone pass the current gate and create two
cards despite containing only default-ignorable question text. Independently
fix this existing visibility boundary; do not expand to generic spoofing,
quality validation or Basic/other-family repair.

Use the Unicode `Default_Ignorable_Code_Point` property, including Mn/Lo
members not already excluded by category C. Verify the chosen property data
and document its fixed version/source; no runtime network lookup or unnecessary
dependency. Preserve saved content containing meaningful text, combining accents,
variation-selector emoji and ZWJ emoji. Do not strip controls from approved
fields. Test each direction and literal/entity forms before insertion, retain
actual-card/count, configured-budget and retry behavior, and record both-core
evidence where available without claiming Qt glyph/end-to-end certification.

Before editing, merge the parent-integrated ownership main commit into this
clean branch and verify it is an ancestor. Do not consult the locked-out
author. Return a committed clean revision with exact changed paths, focused
regressions and remaining acceptance gaps. The parent handles PR integration;
#27 remains open for review UI/lifecycle/budget recovery/acknowledgement gates.
