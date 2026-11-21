### 2026-11-21: Proposed issue #6 runtime and authentication foundation

**By:** functions, accountable session `7cff93fc-c604-45b1-a67d-7fdb0ec98b89`.

**What:** Target Functions v4 with the Python v2 programming model, Python 3.13,
Linux Flex Consumption FC1, zero always-ready instances, 2,048 MB instances and
a five-minute execution budget. East Asia (`eastasia`) is the documented
compatible foundation region, subject to parent data-residency review and
subscription preflight before any infrastructure work.

**Why:** Current Microsoft Learn supports Python 3.13 (GA), and its regional
runtime example explicitly lists East Asia/Python 3.13/FC1. Flex supports
scale-to-zero; classic Linux Consumption does not support Python 3.13 and is
retiring. References and read-only preflight commands are in
`docs/backend-development.md`. No cloud compatibility smoke is claimed.

**What:** Use application-level RS256 bearer verification with fixed public
`AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWKS_URL` settings. Require signature,
issuer, API audience, expiration, issued-at and nonempty subject; validate
not-before when present. Identity is `(issuer, subject)`. Ignore caller identity
headers locally and in Azure. Missing credentials fail 401; unavailable
configuration/signing keys fail 503. The public health route is liveness only.

**Why:** Function keys are not end-user identity, and local routes cannot trust
hosting-style identity headers. This preserves the accepted browser PKCE/API
audience boundary without selecting a provider or implementing uploads/jobs.
Allowed users, operation permissions, ownership and quotas must be designed in
their assigned issues; authentication alone does not authorize artifacts.

**What:** Keep `generation-jobs` as a provisional internal binding, no accepted
job payload schema. Every queue invocation fails explicitly until #8 installs
processing; three host dequeues precede poison placement. No poison consumer,
raw payload logging or success acknowledgement is added.

**Why:** A foundation must not delete unsupported work as if generation
succeeded. Conditional stage ownership, expiry checks, deletion and retry
recovery require the shared #7/#8/#18/#21 contracts.

These are proposed choices for parent reconciliation, not changes to canonical
decisions or authorization to deploy. Requested parent-owned documentation
change: link `docs/backend-development.md` from the root README.
