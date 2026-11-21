### 2026-11-21: Approved Basic import contract

**By:** addon

**What:** Capture a numeric destination bound to its collection; import one
Basic payload only on explicit `approved=True`, reusing the accepted mapper.
Return the saved note ID, revalidated deck and combined Anki changes. The caller
owns review/approval lifetime, serialized collection scheduling, error handling,
duplicate checks and acknowledgement. Model creation is an explicit option and
is a separate Anki write that can survive a failed insertion.

**Why:** This isolates the current issue without implying review UI, atomic
model+note writes or retry safety. The coordinator accepted Anki's logical
numeric-ID boundary, not an incarnation guarantee. Missing or filtered IDs fail,
renames are handled explicitly, and the captured ID is revalidated in the
serialized operation. Existing-deck imports remain enabled, with no name or
Default fallback and no create-new-only substitution.

Real Anki 25.09 core can reuse a deleted deck's numeric ID immediately, with an
identical public deck representation. Both target core versions also
deterministically restore an identical deck dictionary and ID using the public
sync/merge API. Numeric ID alone cannot distinguish either replacement. Desktop
timing/likelihood has not been measured, and post-operation UI hooks alone are
not a proven fence for all writes. See `docs/basic-notes.md`.
