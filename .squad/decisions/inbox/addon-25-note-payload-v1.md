### 2026-11-21: Version 1 generated-note mapper contract proposal

**By:** addon (#25), branch `lucusc-note-model-mapper`, own checkout TEAM_ROOT
and STATE_BACKEND=local.

**What:** Propose the exact wire contract and field mapping in
`docs/note-payload.md`: integer schema_version=1, exact basic/reversed/cloze
model_family, canonical import UUID, family-specific fields, source document
UUID/SHA-256/name/page-slide-section location, bounded producer prompt/model
version labels. No unknown keys/coercion. A producer must persist import_id
before result publication and retain it through retries/review edits.

Use separate `Anki AI Deck Generator::{family}::v1` models via supported
collection APIs; never overwrite built-ins or customized existing models.
Primary fields append Source, Import ID, Payload Version and Provenance.
Import ID is a persisted-field contract after later committed insertion,
not an in-memory dedupe flag or a claim that insertion already occurred.

Balanced limited HTML strips all attributes; unsupported/executable elements,
Anki media/LaTeX markers and malformed/nested cloze fail explicitly.
Source/provenance escape HTML and Anki bracket/brace syntax. Cloze v1 accepts
only nonempty c1-c99 deletions with optional nonempty hints, no nesting/groups.

Mapping is not wired to UI/downloads. Model creation defaults off and requires
explicit boolean permission inside an originating serialized collection
operation. Return unsaved note, ID-revalidated deck and optional model changes.
No note insert/save, approval, duplicate skipping, counts or acknowledgement.

**Why:** Give later generation/review/import issues one precise, reviewable
contract without localized model assumptions, unsafe markup, transient identity
or expansion into #24/#26/#27/#28/#29/#30. Parent/lead must accept/propagate the
proposal before dependent backend work. Numeric #3 deck identity is unchanged.

**Evidence/gates:** 16 focused tests and 61 complete add-on regressions pass,
including real-source mutations for identity, attribute stripping and model
protection. Model APIs inspected on Anki 25.09/26.09.4. Actual desktop saved
rendering/browser views/restart/undo, real persistence and Qt responsiveness
remain unverified; no insertion was performed. Backend/review/import integration
and existing real provider/OS-store/Azure release evidence remain open.
