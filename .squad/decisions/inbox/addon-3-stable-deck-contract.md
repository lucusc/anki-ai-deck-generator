### 2026-11-21: Stable profile-local deck destination proposal
**By:** addon
**What:** #3 carries immutable `DeckIdentity(deck_id, name)` snapshots through a
profile-local `DeckSelection`. Numeric Anki ID is identity; name is local display
metadata, not a lookup key. Refresh retains renamed IDs and rejects missing or
filtered targets without name/default fallback. Future review/import must
capture the target with its collection lifetime and call `revalidate_deck()`
inside the same serialized collection operation immediately before writing.
Profile close clears the holder; no persistent/backend deck mapping is invented.
Creation is explicitly user-directed, validates names before collection access,
and uses Anki's supported CollectionOp/change-result boundary. Local selection
does not require network auth but existing public configuration failures still
prevent opening the workflow, preserving #1's explicit configuration boundary.
**Why:** Names can change or be reused after deletion, while current-deck or
default fallback can silently import into an unintended collection destination.
Serialization keeps collection work responsive and separate from auth workers.
Actual later review/import wiring remains owned by its tracked issues.

Both 25.09 and 26.09.4 expose the inspected APIs; synthetic packaged-load tests
are not real desktop/undo certification. Closing during an already-started
creation may leave the committed deck; it is never silently rolled back.
Parent acceptance/reconciliation is explicit, not live shared state.
