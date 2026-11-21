### 2026-11-21: Audience-only immutable settings integration
**By:** addon
**What:** Implement the parent-accepted required `audience` field and five exact
wire values in separate dependency-free client/server enums and frozen
`AudienceSettings` projections. Client capture and server
`contracts.validate_audience_settings` fail explicitly on missing/unknown
values, with no default, alias or whitespace coercion. Fixed `review_label`
comes from the accepted snapshot, not the current combo. Invalid reselection
clears the live choice; prior captured settings remain unchanged.
**Why:** Later UI changes and mutable request/output dictionaries must not alter
an accepted audience. Separate distributable runtimes cannot import each
other's packages; golden-value and round-trip validation tests enforce parity.

Integration proposal for parent reconciliation: #7 must validate the parsed
request settings before acceptance/persistence/enqueue; #8 must restore and
validate persisted settings and preserve them in private results; #5 must
reconstruct/display the accepted snapshot rather than live UI state. The
projection intentionally does not accept/define a full job or result schema,
or validate other settings. #19/#20 must include audience in compatibility
identity. OAuth token audience and study audience remain separate fields in
separate models. Profile/ownership/expiry checks remain caller responsibilities.

Current UI summary, immutable contracts and offline parity are implemented.
Actual job/review boundaries and real Anki/provider smoke remain open, so the
full live #4 job/review acceptance is not reported as end-to-end complete.
