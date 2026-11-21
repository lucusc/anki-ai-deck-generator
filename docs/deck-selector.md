# Deck selector (#3)

This slice adds a local destination selector to the **existing single Tools >
Anki AI Deck Generator** modeless workflow. The #1 foundation document describes
the earlier sign-in-only milestone; this document describes the additional #3
behavior. There is no upload, audience selector, review screen or note import.

## Using the selector

Valid public OAuth configuration is still required to open the workflow.
Missing/invalid configuration continues to show the original actionable error;
deck selection does not disguise an authentication/configuration failure.
Local selection and explicitly requested creation do not require a network
sign-in or access token.

Opening the workflow asynchronously lists normal collection decks, including
an empty Default deck. Filtered decks are excluded and identified as ineligible
import destinations in the UI. No deck is initially selected automatically.
Choosing a list item selects its numeric ID without changing Anki's current
study deck or writing notes.

**Create new deck** is the only creation action. Entering a name or selecting
an existing deck does not create anything. Hierarchical `Parent::Child` names
are supported; Anki may create the necessary parent deck. Names are normalized
to Unicode NFC. Empty names/components, component-edge whitespace/colons,
control characters and double quotes are rejected before collection access,
rather than letting Anki silently change them to another name. Existing names
(including case-insensitive matches and filtered decks) must be selected
instead of created again.

Use **Refresh decks / check selection** after editing decks elsewhere in Anki.
Reopening the existing Tools window also refreshes when idle. A renamed
selection keeps its ID, updates its displayed name and shows an explicit rename
notice. A deleted/filtered selection shows an error and an empty combo selection;
it never falls back to Default or a replacement with the same name. The old
target remains available only as an invalid reference requiring revalidation
or explicit reselection.

## Reusable local destination contract

- `models.deck.DeckIdentity(deck_id: int, name: str)` is an immutable snapshot.
  The numeric Anki ID is identity; the name is only local display metadata.
  Its representation is redacted, and neither IDs nor names are logged.
- `DeckSelection.target` holds that snapshot across closing/reopening the
  workflow within the same profile. Profile close clears it. It is not saved
  to add-on configuration, transferred to another profile or persisted across
  Anki restarts.
- Future review/import code must capture this immutable target together with
  its originating collection/profile lifetime, not a combo index or deck name.
  Call `services.decks.revalidate_deck(collection, captured_target)` inside the
  serialized collection operation immediately before use. It resolves only
  the ID among normal decks, returning the current name; compare the snapshot
  name to show a rename notice. Missing/filtered/unselected/unavailable targets
  raise fixed `DeckError` messages. Never resolve a missing ID by name/default.
- Revalidation and subsequent import must share the same collection operation
  so another operation cannot delete the target between the check and write.
  Actual import, review state and any backend/user-scoped logical deck mapping
  belong to their tracked issues; this contract is a proposal for reconciliation,
  not an adopted backend request shape.

## Collection access, cancellation and privacy

Reads use collection-bound `QueryOp`, without blocking the main thread.
Creation uses `CollectionOp` and `col.decks.add_normal_deck_with_name()`,
preserving Anki's changes/undo/UI notifications. No SQL, private collection
internals, legacy deck dictionaries or default-fallback lookup is used.
Duplicate lookup and creation run in one serialized collection operation.
Widget updates run only in main-thread completion callbacks.

Authentication still uses `QueryOp.without_collection()` and the unchanged
PKCE/protected-refresh services. Deck controls are disabled during network/store
work, and authentication controls are disabled during deck operations. Neither
starts through this workflow while the other is pending.

Cancel, window close and profile close mark pending deck work cancelled before
collection access and ignore late UI callbacks; profile close also clears the
target and cancels authentication. A short creation already executing can
commit despite closing the window. It is not rolled back or silently deleted;
reopen/refresh to see it, or use Anki's normal undo/deck controls. No private
content or raw exception is shown/logged; expected failures use fixed deck
codes and unexpected failures use the existing `internal` error.

## Evidence and remaining desktop gates

The selected targets remain **Anki 25.09 and 26.09.4, Qt6 desktop**. Both tags
were inspected for:

- [`all_names_and_ids`, `id_for_name`, `add_normal_deck_with_name` (25.09)](https://github.com/ankitects/anki/blob/25.09/pylib/anki/decks.py)
  and [26.09.4 deck APIs](https://github.com/ankitects/anki/blob/26.09.4/pylib/anki/decks.py).
- [25.09 collection/query operations](https://github.com/ankitects/anki/blob/25.09/qt/aqt/operations/__init__.py)
  and [26.09.4 operations](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/operations/__init__.py).
- [25.09 supported deck creation operation](https://github.com/ankitects/anki/blob/25.09/qt/aqt/operations/deck.py)
  and [26.09.4 creation operation](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/operations/deck.py).
- [26.09.4 name normalization](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/decks/name.rs).

Focused synthetic tests cover existing selection, explicit creation, invalid and
duplicate names, renamed/deleted/name-reused/filtered targets, profile/window
cancellation, late callbacks, auth/collection dispatch separation, content-free
errors and both version-labeled packaged-load doubles. Real-source mutations
prove ID-based revalidation and pre-write name validation assertions fail for
regressions; the existing auth mutation checks remain active.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s addon/tests -v
python3 addon/tools/build.py /tmp/anki-ai-deck-generator.ankiaddon
```

These are API-double/package tests, **not real Anki desktop certification**.
In disposable synthetic profiles on both targets/platforms, still verify
empty/default/hierarchical and filtered deck listings; create/undo a normal deck;
rename/delete while the modeless workflow is open; refresh/reopen; close/switch
profiles during queued operations; and confirm normal Anki remains responsive.
Actual Qt event-loop/restart/undo, OS-store and approved-provider smoke tests
remain release gates. No Azure deployment/provider verification was performed.
