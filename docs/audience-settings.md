# Audience selector and settings contract (#4)

The existing single **Tools > Anki AI Deck Generator** modeless workflow now
offers the five product audiences. This is an audience selector and reusable
settings contract, **not implemented job submission, generation or review**.
The earlier foundation/deck documents describe their respective milestones;
this document describes the additional audience behavior.

| Product label | Exact `audience` wire value |
| --- | --- |
| Middle School | `middle_school` |
| High School | `high_school` |
| University | `university` |
| Certification | `certification` |
| Professional | `professional` |

## Current workflow

No audience is selected by default. The placeholder requires an explicit
choice; choosing an audience displays a read-only `Audience: <product label>`
summary using the same snapshot label that future review code will consume.
This does not change the selected destination deck, Anki's study deck or any
notes, and makes no network request or collection write.

The selection survives closing/reopening the dialog within the same profile.
Profile close clears it; it is not saved to config or across Anki restarts.
As with deck controls, audience controls are disabled during authentication
and collection operations. Closing the workflow disables the selector and
ignores late selection callbacks. Missing or invalid OAuth configuration still
fails explicitly before opening the workflow; audience selection does not
bypass sign-in configuration or change PKCE/protected refresh storage.

## Immutable client and server projection

`addon.models.audience.AudienceSettings` and
`backend/contracts/audience.py`'s `AudienceSettings` are frozen, validated
**audience-only projections**, not an accepted full job schema. Each contains
one `Audience` enum member, without a default. The server package exports
`validate_audience_settings(settings)`, `AudienceSettings`, `Audience` and
`AudienceError` through `contracts`.

`from_mapping()` / the server validator require a mapping with an explicit
`audience` field of exactly one of the five JSON string values above.
Missing fields raise `AudienceError` with code `missing`. Unknown strings,
labels, aliases, case changes, whitespace, null, booleans, numbers, lists,
enum objects on the wire and non-mapping settings raise code `invalid`.
Neither validator coerces inputs, substitutes an audience or echoes rejected
values. Additional keys are deliberately not validated or retained by this
projection; the future full job validator must validate its other fields.
Direct construction requires an `Audience` enum, never a raw string or null.

`to_mapping()` returns a fresh `{"audience": "<exact wire value>"}` dictionary.
Mutating that dictionary or the input mapping cannot change the snapshot.
`review_label` derives the fixed product label from the captured enum.
Representations are redacted; the UI/validator emits no audience/study metadata
to logs. These fields are distinct from the deployment-configured OAuth/API
token audience, which lives in `OAuthConfig`, not study job settings.

For later client submission, capture the explicit selection:

```python
captured_audience = dialog.audience.capture_settings()
audience_fields = captured_audience.to_mapping()
# Future job settings must include audience_fields["audience"] explicitly.
# Future review must display captured_audience.review_label, not the live combo.
```

Missing selection raises `missing`; capture from a closed selector raises
`closed`. An invalid new choice clears the current selection and reports the
error, rather than silently reusing a previous audience. Already captured
snapshots stay unchanged when the user selects another audience or closes the
dialog. A snapshot alone is not authorization or proof that the originating
profile/collection, job or artifact is still usable.

## Required future integration (not implemented here)

1. **#2/#7 submission:** capture audience together with the immutable deck and
   future full settings snapshot; send the explicit `settings.audience` field.
   In the authenticated #7 acceptance boundary, call
   `contracts.validate_audience_settings(request_settings)` on the parsed
   `settings` object **before accepting/persisting/enqueuing a job or reserving
   billable processing**. Map `missing` / `invalid` to a content-free 400
   validation response; do not enqueue, use a default or return 202 on failure.
   Auth, user ownership, quotas and retention must still be independently
   enforced. No existing handler currently invokes this validator.
2. **#8 processing:** restore/validate the persisted accepted settings with the
   same server validator at the worker boundary. Do not replace the accepted
   audience from model output or current client state. Preserve its wire value
   in the immutable private result/settings contract. #19/#20 compatibility
   identity must include audience plus relevant settings/pipeline versions.
3. **#5 review:** reconstruct `AudienceSettings` from the accepted job/result
   settings and display its `review_label`. Missing/invalid result settings
   must fail explicitly, not fall back to the current UI selection. Check
   job ownership, originating profile lifetime and artifact expiry separately.
   The current read-only selector summary is **not** the future review screen.

These caller/schema/HTTP/result integrations remain tracked prerequisites.
The full live #4 job-settings/review acceptance is not claimed complete merely
because the reusable contract and current UI exist.

## Evidence and manual gates

Synthetic tests cover all five exact option/label pairs, no initial default,
client/server serialization and validation parity, missing/unknown/type errors,
immutable request/output/UI snapshots, invalid reselection, profile/window
lifetime, busy-control recovery, selected-deck preservation and packaged
workflows using both **Anki 25.09 and 26.09.4 Qt6 API doubles**. Real-source
mutations demonstrate tests reject default substitution, unknown-value
fallback, a mutable snapshot and an automatically selected first option.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s addon/tests -v
cd backend
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest
```

The #4 run passed **54 add-on tests** on CPython 3.14.0 and
**100 backend/storage tests** on CPython 3.13.9, including 23 server audience
cases. No Azure calls, paid services
or runtime agents were added. Package-load tests exercise the actual builder
and extracted artifact, not an installed Anki application.

Actual desktop/Qt event-loop/OS-store/provider smoke remains **unperformed**.
On both target versions/platforms in disposable synthetic profiles, verify
the placeholder, all five options/labels, dialog reopen/profile reset, disabled
controls during authentication/deck work, unchanged destination selection
and continued Anki responsiveness. After #7/#8/#5 integration, verify the
submitted/persisted audience survives later UI changes and appears unchanged
on review, and malformed/missing values return an explicit server error.
No end-to-end job/review, deployed provider or Azure verification is claimed.
