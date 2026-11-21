### 2026-11-21: Reversed import count, budget and logical retry contract

**By:** addon

**What:** `capture_reversed_target` shares Basic's collection-bound logical
numeric target. `import_approved_reversed(..., approved=True,
remaining_cards=<required exact nonnegative int>, create_model=False)` imports
only reversed v1 into the existing strict managed model; creation remains
opt-in. Basic's public API/behavior is unchanged; only its private snapshot
helper is extracted for reuse.

The result exposes one saved note, two actual saved card IDs and their count,
plus separate added counts. New imports consume two explicit remaining cards;
zero/one rejects before model/insertion writes. Matching retries consume zero,
even with remaining_cards=0. Caller must maintain/reconcile its serialized
job/review budget; no unlimited/global quota default or durable job ledger exists.

Collection-wide canonical Import ID search is followed by exact UUID comparison.
A single compatible saved note with identical sanitized fields/provenance/model
and both destination cards is reused. Conflicting/ambiguous identity, altered
content/source/versions, other family/model, moved/missing cards fail visibly,
without insertion or repair. Scheduling/tags are preserved and not compared.
This is logical import-ID retry reconciliation, not generic #24 hash dedup.

Render both actual saved directions; reject question text composed solely of
whitespace/control/format characters. Preserve format controls in otherwise
visible text, including ZWJ emoji. The parent directed this gate to remain
reversed-only; Basic's adjacent pre-existing U+200B visibility gap is documented,
not expanded into other-family markup work.

**Why:** Both real cores save two cards per normal reversed note and report
`add_note.count=2`, which must not be displayed as two notes. Empty Front,
format-only fields and custom conditions have different actual core-generation/
render behavior, so template count alone is not evidence. Canonical saved
identity permits recovery after a committed write whose acknowledgement failed
without auto-updating conflicts or inventing generic hash workflows.

**Evidence:** macOS CPython 3.13.9: 27 focused Basic/reversed and 97 full add-on
tests pass on each core 25.9/26.9.4. CPython 3.14 standard-library suite passes
97 with 16 explicit core skips. Synthetic temporary collections close/reopen,
inspect saved IDs/faces, test budgets, zero-add retries, conflicts, custom model
preservation, visibility, failures and source mutations.

**Boundaries:** Caller approval/lifetime/serialization/budget recovery and Anki
commit confirmation remain required. Model creation/insertion are separate
writes; failure can leave model/note state requiring reconciliation. No protection
against arbitrary third-party hook writes, user deletion/edit of identity,
or indistinguishable same-ID replacement is promised. No installed Qt desktop,
profile/cancellation/undo/full application restart, review UI count display,
backend acknowledgement/retention or end-to-end acceptance is claimed.
Detailed contract and gaps: `docs/reversed-notes.md`.
