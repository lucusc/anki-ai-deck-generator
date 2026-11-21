# Approved Basic-note import (#26)

This slice supplies an import helper, not a review screen or a complete workflow.
It imports one explicitly approved Basic note into a captured normal deck, using
the existing version-1 mapper, formatting rules and isolated managed model.
It does not import reversed/cloze notes, implement duplicate detection or send
backend acknowledgements.

## Proposed caller contract

`capture_basic_target(collection, selected_deck)` captures and revalidates the
selected `DeckIdentity` within the originating profile's serialized collection
operation. The result binds the numeric deck ID to that collection object.
Selection must have an exact positive integer ID; it is not resolved by name.
An unselected, invalid, missing or filtered destination fails explicitly.

After the user has reviewed the exact note, call
`import_approved_basic(collection, reviewed_wire_note, captured_target,
approved=True, create_model=True)` **inside a serialized collection operation**.
The caller supplies `approved=True` only for that reviewed note; the helper is
not itself a review UI or proof of human approval. Every other value, including
`False`, `None` and `1`, fails before any collection access. The caller must
capture the reviewed content and approval together, invalidate approval on
edits, and enforce profile/window cancellation and collection-lifetime checks
before scheduling and again inside the operation. A collection-object identity
check rejects a different/reopened collection, but does not replace those
profile-lifetime and cancellation checks.

Only a validated `basic` version-1 payload is accepted. A private snapshot of
the parsed fields and source prevents later changes to the caller's object from
changing what the mapper imports. The mapper revalidates the captured ID within
the same serialized operation immediately before model resolution and insertion.
An ordinary rename retains the ID and returns the current display name; a
missing/filtered ID fails rather than falling back to Default or another name.

**Known identity limitation:** Anki 25.09 core was observed deleting and
recreating a deck with the *same* numeric ID and identical public deck
representation within one millisecond. Separately, a deterministic synthetic
test on both core versions saves the public deck dictionary, removes the deck,
and restores the identical dictionary with the public `decks.update(...,
preserve_usn=True)` sync/merge API. The ID, full returned dictionary and result
of ID-only revalidation are identical. These core experiments do not establish
how frequently either situation occurs through the desktop UI. An ID/name or
metadata fingerprint cannot prove incarnation continuity. This prerequisite
contract gap requires a broader profile/deck-lifetime solution or an accepted
fail-closed boundary; this slice does not invent an unsupported identity or
modify the selector.

The public [operation completion hook](https://github.com/ankitects/anki/blob/25.09/qt/tools/genhooks_gui.py)
is a UI notification after an operation, not a proven fence for all writes.
In particular, `CollectionOp` posts completion callbacks to the main thread,
and a failed operation does not fire its success notification. Direct collection
mutations, sync/import and lifecycle changes need separate consideration. Do
not claim that hook-only invalidation protects every pending import.

The mapper strips unsafe attributes and rejects unsupported/executable markup
and Anki media/LaTeX syntax as described in [note-payload.md](note-payload.md).
Source display and provenance use its existing escaping. The helper calls
`Collection.add_note(note, deck_id)` with the revalidated ID; the managed model
has one forward template and never overwrites customized models.

Model creation remains **opt-in**: omit `create_model` or pass `False` to require
an existing model. Passing `True` is appropriate only within this approved,
user-directed operation; non-boolean values fail. The returned
`BasicImportResult` contains the saved note ID, updated deck snapshot,
`note_changes`, optional `model_changes`, and a combined `.changes` suitable
for Anki `CollectionOp` notifications. Model creation and note insertion are
separate Anki operations, not one atomic undo step. If creation succeeds and
insertion raises, the model can remain; the exception propagates, no result is
returned, and the caller must refresh collection UI/state and report the failure.
Unexpected storage failures can leave an ambiguous outcome; never silently
retry insertion or report success. The caller must not acknowledge backend
import until it has confirmed the collection operation committed.

The saved `Import ID` enables a future duplicate/retry design, but this helper
does **not** check it. Repeating an approved call can insert another note.
Do not use it as a retry-safe integration until #24 and the review/import
workflow provide that check, partial-failure recovery and acknowledgement.
Existing local originals and imported collection data are never deleted here.

## Verification and release gaps

The default add-on suite uses synthetic doubles and skips real-core tests when
`anki` is unavailable. To run the real-core checks in separate disposable
Python 3.13 environments:

```sh
python3.13 -m venv /tmp/anki-basic-25
/tmp/anki-basic-25/bin/python -m pip install 'anki==25.9'
PYTHONDONTWRITEBYTECODE=1 /tmp/anki-basic-25/bin/python -m unittest discover -s addon/tests -p test_basic_notes.py -v

python3.13 -m venv /tmp/anki-basic-26
/tmp/anki-basic-26/bin/python -m pip install 'anki==26.9.4'
PYTHONDONTWRITEBYTECODE=1 /tmp/anki-basic-26/bin/python -m unittest discover -s addon/tests -p test_basic_notes.py -v
```

Real Anki core checks use temporary synthetic collections. They save and close
the collection, reopen it, inspect the saved fields/identity/deck, and render
both card faces; they also check no model/note is created for unapproved input,
rename preservation, deletion/name reuse when IDs differ, and deterministic
restoration of indistinguishable deck data. Unit tests cover
approval types, invalid/unsupported notes, markup, collection mismatch,
model-creation permissions, propagated errors and source mutations of the
approval/family gates.

On macOS with CPython 3.13, the complete add-on suite passed **81 tests** with
each of Anki core 25.9 and 26.9.4 installed. The standard-library-only run passed
81 tests with the three real-core checks skipped.

These are **core-library** checks, not installed Anki/Qt desktop tests or a
full application restart. Actual 25.09 and 26.09.4 Qt rendering, browser/reviewer
views, profile switch/cancellation, undo behavior and responsive collection
operations remain unverified. Review-screen integration, stable identity under
same-ID reuse, duplicate-safe retry and backend acknowledgement remain open.
