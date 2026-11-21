# Approved Basic and reversed import (#27)

This is a collection-operation helper, not a review screen or complete import
workflow. It saves one explicitly approved version-1 `reversed` note, verifies
both actual cards and their rendered faces, and reconciles a matching logical
import identity without inserting again. Basic's public API remains unchanged.
No backend acknowledgement, generic concept/hash deduplication (#24), other note
family, UI, deployment or runtime agent is implemented.

## Caller API and card budget

```python
from addon.services.reversed_notes import (
    capture_reversed_target, import_approved_reversed,
)

# Both capture and import belong inside the originating serialized collection operations.
target = capture_reversed_target(collection, selected_deck)
result = import_approved_reversed(
    collection, reviewed_wire_note, target,
    approved=True, remaining_cards=remaining_job_cards, create_model=True,
)
remaining_job_cards -= result.added_card_count
```

`capture_reversed_target` reuses Basic's collection-bound `BasicImportTarget`
and exact positive numeric `DeckIdentity` validation. Revalidation immediately
before import retains ordinary renames, rejects absent/filtered targets, and
never resolves by name or falls back to Default. The accepted target is a
**logical numeric ID, not a deck-incarnation guarantee**: identical same-ID
restoration/recreation cannot be distinguished through that contract.
Existing-deck imports remain enabled. See [Basic's limitation](basic-notes.md).

`approved` must be exactly `True`, not `1` or a truthy value. The helper cannot
prove human review. Capture content and approval together, invalidate approval
on edits, and check originating profile/window/cancellation before scheduling
and again inside the operation. A reopened/different collection object fails;
object identity does not replace caller lifecycle checks or Qt integration.

`remaining_cards` is a **required keyword**, with no implicit unlimited/global
quota default. It must be an exact nonnegative integer; booleans, floats,
strings, missing values and negatives fail. A new approved note requires two
remaining cards. Budgets of zero or one reject before model creation/insertion.
A matching retry with zero remaining is permitted because it adds zero cards.
For a serialized batch, subtract each successful `added_card_count` from the
explicit job/review budget before the next import. Do not reset the budget for
each note, count `add_note().count` as notes, or count existing retry cards as new.
The caller must reconcile successful imports after partial failure; this helper
does not persist a job budget ledger or enforce a backend atomic user quota.

The result is a frozen, content-free-repr `ReversedImportResult`:

| Field/property | New import | Matching prior import |
| --- | --- | --- |
| `note_id` | Saved note ID | Same prior note ID |
| `deck` | Revalidated numeric target/current name | Same revalidated target |
| `card_ids` | IDs read from the actual saved cards | Same prior actual card IDs |
| `note_count`, `card_count` | 1, 2 | 1, 2 |
| `added_note_count`, `added_card_count` | 1, 2 | 0, 0 |
| `reused` | `False` | `True` |
| `note_changes`, `model_changes` | Anki insertion changes, optional creation changes | Both `None` |
| `.changes` | Combined Anki changes for `CollectionOp` notification | Empty Anki `OpChanges` (no write) |

Anki's `add_note().count` is **two generated cards**, not one note, on these
supported cores. The result uses actual saved card IDs rather than a template
count. It verifies ordinals 0/1, the same saved note ID and destination on both
cards, and renders both faces. Strict model validation and pre-insertion
question rendering establish the two-card requirement before insertion.

## Compatible model and visible questions

Use only `Anki AI Deck Generator::reversed::v1`, the existing mapper's normal
model with exact `Front`, `Back`, `Source`, `Import ID`, `Payload Version`,
`Provenance` fields and fixed CSS. `Forward` asks `{{Front}}` and answers
`{{FrontSide}}<hr id=answer>{{Back}}` plus Source; `Reverse` asks `{{Back}}` and
answers `{{FrontSide}}<hr id=answer>{{Front}}` plus Source. Both cards refer to
one note's fields, including the same canonical generated-note import UUID.
The UUID is not displayed on either face.

User built-ins and arbitrary custom models are never edited or selected.
Customized managed question/answer/browser formats, template deck overrides,
fields or CSS fail via the mapper, without repair or fallback. Creation is
opt-in and requires an exact boolean `create_model=True`. An existing model
must remain compatible on retries too. No migration or custom-model adapter is
provided; resolve the collision explicitly before retrying.

The mapper already rejects empty/HTML-only/whitespace/NBSP-only fields and strips
hidden/event/style attributes. Actual-core experiments bypassing the importer
show why neither field-string presence nor template count is enough:
an empty Front generates only the Reverse card; `<b></b>` and `&nbsp;` generate
two cards despite a visually blank Forward question. Conditional custom
questions can generate a single fallback card whose faces report a blank front.
Those synthetic bypasses characterize Anki, not accepted import inputs.

The existing mapper also accepts U+200B-only text; both cores create two cards
with an invisible Forward question. The reversed helper rejects that case
before note insertion, including entity-encoded U+200B, by testing each core
rendered question's HTML-stripped text for a non-whitespace, non-Unicode-control/
format character. It does **not** remove format controls from saved text:
mixed visible/U+200B text and ZWJ emoji remain unchanged. This is a bounded
text-visibility gate, not semantic quality validation, a Unicode spoofing
detector or proof of Qt glyph availability. The adjacent Basic-only helper's
invisible-Unicode gap is pre-existing and unchanged; broader repair is outside
this assignment.

## Retry identity and failure boundaries

Immediately before insertion, search the originating collection with the
canonical UUID in `Import ID`, then compare the full stored field value exactly.
Search is deliberately collection-wide: reusing the UUID in another family or
destination is a conflict, not permission to add a second copy. Multiple exact
matches also fail. This is local logical import-ID reconciliation, not concept
hashing, semantic deduplication or a generic cross-family #24 workflow.

A single prior note is reused only if its managed model ID and all mapped fields
equal the approved sanitized snapshot, including Source, Payload Version and
escaped canonical Provenance. Both saved directions must still exist in the
captured destination and render visible questions. Different content/source/
prompt/model versions, user field edits, moved/missing cards, another model or
ambiguous identity cause an explicit error without insertion or modification.
Equivalent raw HTML that sanitizes to the same fields is matching; scheduling
and user tags are not compared or modified.

Review edits retain the producer-assigned UUID. Edits before the first import
are accepted; changing approved content after that UUID was saved is a conflict,
not an implicit update. The caller must guide deliberate reconciliation.
Deleting/editing `Import ID`, changing models, or removing imported notes can
invalidate recovery; protection against arbitrary user edits or indistinguishable
logical identity replacement is not promised.

Unexpected Anki/storage/render errors propagate, never become success. A write
can commit before an exception/lost acknowledgement; inspect the collection via
the same approved identity on explicit retry, rather than blindly inserting.
Model creation is a separate Anki write and can persist after failure. If saved
content/cards differ from approval, a content-free `saved_state`/`cards` error
requires reconciliation; the helper does not delete or auto-undo user collection
data. Third-party hooks that mutate models/content during insertion can violate
the prechecked assumptions; detected differences are not success, and this is
not a transaction fence against arbitrary third-party modifications. Do not
reuse a stale budget or acknowledge backend import on a failure.

Only acknowledge after the caller has confirmed committed collection state.
Pass `.changes` to normal operation notifications; refresh UI/state on failures
that may have written. No unified undo/profile/Qt/review/ack implementation or
backend-retention integration is claimed. No local originals, media or notes
are deleted by this helper.

## Evidence and remaining acceptance gaps

Run `python -m unittest discover -s addon/tests -p 'test_*notes.py' -q` in
separate disposable Python 3.13 environments with real `anki==25.9` and
`anki==26.9.4`. See [Basic verification setup](basic-notes.md). The full add-on
suite remains `python -m unittest discover -s addon/tests -q`.

Focused tests create temporary synthetic collections on both cores, inspect
actual saved cards and both faces after close/reopen, and verify two-card budgets,
zero-add retries, identity/content/destination conflicts, preserved custom
built-ins, managed collision rejection, format-only output, U+200B rejection and
mixed-format/ZWJ preservation. They cover ambiguous post-commit failures,
pre-write outages, post-write content changes and source mutations of the real
budget/retry gates. Core tests are explicitly skipped if Anki is unavailable.

On macOS/CPython 3.13.9, **27 focused Basic/reversed tests and all 97 add-on
tests passed on each of Anki core 25.9 and 26.9.4**. The standard-library-only
CPython 3.14 run passed 97 tests with 16 real-core checks explicitly skipped.

Actual installed **25.09/26.09.4 Qt desktop**, browser/reviewer rendering,
responsive operations, profile/window/cancellation, undo/application restart,
review-screen count display, batch-budget recovery and backend acknowledgement/
retention integration remain unverified acceptance/release gates. Core saved-face
rendering is not those desktop/end-to-end checks; #27 is not fully closed by
this helper alone.
