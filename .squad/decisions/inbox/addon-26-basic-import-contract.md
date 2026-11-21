### 2026-11-21: Approved Basic import contract proposal

**By:** addon

**What:** Capture a numeric destination bound to its collection; import one
Basic payload only on explicit `approved=True`, reusing the accepted mapper.
Return the saved note ID, revalidated deck and combined Anki changes. The caller
owns review/approval lifetime, serialized collection scheduling, error handling,
duplicate checks and acknowledgement. Model creation is an explicit option and
is a separate Anki write that can survive a failed insertion.

**Why:** This isolates the current issue without implying review UI, atomic
model+note writes or retry safety. Real Anki 25.09 core can reuse a deleted deck's
numeric ID immediately, with an identical public deck representation. Numeric
ID alone cannot distinguish that replacement; the parent must reconcile a
broader stable-deck lifetime mechanism before accepting a complete identity
guarantee. See `docs/basic-notes.md` for evidence and remaining gates.
