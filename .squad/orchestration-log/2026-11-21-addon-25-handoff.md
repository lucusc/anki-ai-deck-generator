# Issue #25 addon handoff

| Field | Value |
| --- | --- |
| Member/session | addon / `6aee107a-063e-41f5-b872-4a39b748c2a7` |
| Ownership | `2026-11-21T030500Z-addon-issue-25.md`; no scope expansion |
| TEAM_ROOT/WORKTREE_PATH | Own `lucusc-silver-couscous` checkout; STATE_BACKEND=local |
| Final branch | `lucusc-note-model-mapper` |
| Parent identity | `53116c8` applied as `047a559` before implementation |
| Main integration | Merged bootstrap `22258947c0fb0e6ed98b2866b94511492db6cbee` |
| Implementation | `c1ce981d6c2f21244712831c4a841ef99b91e6f7` |
| Outcome | Review-ready scoped implementation; real-desktop/integration gates open |
| Publication | User-directed `gh` PR to main; parent reviews/merges serially |

## Paths

- `addon/models/note_payload.py`
- `addon/services/note_models.py`
- `addon/services/markup.py`
- `addon/tests/test_note_models.py`
- `addon/tests/test_markup.py`
- `docs/note-payload.md`
- `.squad/decisions/inbox/addon-25-note-payload-v1.md`
- `.squad/agents/addon/history.md` (append only)
- This unique handoff record

Existing Tools/sign-in/deck/audience UI, backend, root manifests/README and
canonical backlog/decisions were not independently edited.

## Acceptance evidence

Typed/versioned wire parser covers exact Basic/reversed/Cloze field shapes,
strict version/UUID/source/version labels and explicit trusted field errors.
Separate versioned models use public Anki model/new-note APIs; built-ins remain
unchanged and customized/colliding managed models fail without overwrites.
All HTML attributes are removed; unsupported/executable HTML, Anki LaTeX/sound
and malformed cloze fail. Source/provenance become inert display metadata.

Import ID/Payload Version/Provenance are mapped to actual note fields, not
transient state. Model creation is explicit/default-off and returns changes.
Notes remain unsaved; no #24/#26/#27/#28/#29/#30/import workflow claimed.
Numeric captured deck ID is revalidated with the accepted #3 helper.

Proposal: schema_version=1; model_family basic/reversed/cloze; import_id canonical
UUID; fields Front/Back or Text/Back Extra; source document_id/sha256/name with
required nullable page/slide/section location; prompt_version/model_version
bounded producer labels. See docs/note-payload.md for exact validation, names,
templates, persisted field shapes and producer/caller responsibilities.

## Verification

- `cd addon/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_note_models test_markup -q`: **16 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s addon/tests -q`: **61 passed**.
- Tests include real-source mutation failures for persistent Import ID,
  attribute removal and managed-model preservation; malformed payload/source,
  exact size boundaries, entity/tag-split Anki syntax and cloze cases.
- Synthetic collection API double verifies exact model/field/template artifacts,
  no note insertion, copied-model reuse, explicit creation/errors and stable
  deleted/renamed/filtered deck handling. This is not real disk persistence.
- Local build verified mapper modules in package and tests excluded; artifact
  kept outside the repository in this session's files.
- `git diff --check`: passed.
- Public model/collection APIs inspected on both Anki 25.09 and 26.09.4.

## Open safety/release/integration gates

Real Anki writes/undo, saved question/answer and browser rendering after restart,
disk persistence and Qt responsiveness on both targets/platforms are unverified.
No notes were inserted and no disposable desktop profile was used.
Producer contract must be parent/lead accepted before dependent generation.
Later approved import must perform profile/collection-lifetime checks, revalidate
deck/model inside its serialized write, find persisted identity, commit, handle
partial retry and acknowledge afterward. Existing OS-store/provider/Azure gates
remain open. No deployment, paid calls, nested agents/sessions or watchers.

This record reports offline #25 mapping evidence, not issue closure or V1
certification. Parent owns acceptance, shared-state reconciliation and PR merge.
