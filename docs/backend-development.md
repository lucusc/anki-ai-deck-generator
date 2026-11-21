# Backend development

Issue #6 establishes a Python Azure Functions **v2 programming model** app in
`backend/`, using the **Functions v4 host**. This is not a working generation
service. No uploads, job payload contract, storage schema, paid calls, deployment,
or runtime agents are implemented.

## Runtime and Consumption choice

The foundation targets **Python 3.13, Linux Flex Consumption, SKU FC1,
East Asia (`eastasia`)**, with **zero always-ready instances** and an initial
2,048 MB instance size. Flex scales to zero; storage and telemetry can still cost
money while compute is idle. The region is a documented compatible foundation
target, not an approved production data-residency decision.

Authoritative Microsoft documentation checked on 2026-11-21:

- [Supported languages](https://learn.microsoft.com/azure/azure-functions/supported-languages):
  Python 3.13 is GA with expected support through October 2029; Python runs on
  Linux. Do not confuse the v2 programming model with the host version.
- [Flex Consumption](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan):
  Python 3.13 is supported; always-ready defaults to zero and 2,048 MB is the
  recommended general-purpose size. Classic Linux Consumption is retiring,
  and does not support Python versions newer than 3.12.
- [Regional runtime example](https://learn.microsoft.com/powershell/module/az.functions/get-azfunctionappflexconsumptionruntime):
  the East Asia example explicitly lists Python 3.13 and FC1.
- [Create/manage Flex](https://learn.microsoft.com/azure/azure-functions/flex-consumption-how-to):
  availability is regional and must be checked again for the target subscription.

Before future authorized infrastructure work (#34), confirm the desired region
and runtime using the portal or the read-only commands below. They require an
authenticated Azure account; no cloud check was performed for this foundation.
Do not silently substitute another SKU or region if a check fails.

```sh
az functionapp list-flexconsumption-locations -o table
az functionapp list-flexconsumption-runtimes --location eastasia --runtime python -o table
```

`host.json` bounds each execution to five minutes. Future workers must checkpoint
and split processing within that budget; Flex's longer possible timeout is not
permission to run generation inside HTTP. Queue concurrency settings bound one
instance, not global per-user capacity or atomic quotas.

## Offline tests (no Azure credentials or running host)

Use Python 3.13 and a local virtual environment. From the repository root:

```sh
cd backend
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Tests invoke the real decorated Functions handlers and inspect SDK-generated
bindings. Tokens and RSA keys are synthetic and generated in memory; JWKS lookup
is replaced only in tests. Tests never call an identity provider, Azure storage
or AI. Pinned direct dependencies live in `requirements*.txt`; transitive
dependencies are not locked yet.

## Optional local Functions host

Install [Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
and [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
only when needed. Run Azurite on loopback with its data/log directory **outside
the repository**; it is an emulator, not secure production storage. In another
terminal:

```sh
cd backend
cp local.settings.json.example local.settings.json
source .venv/bin/activate
func start
```

The template contains only the emulator shortcut `UseDevelopmentStorage=true`
and empty public authentication settings, never cloud credentials. Local settings,
virtual environments and caches are ignored in Git; `.funcignore` also excludes
local settings, templates and tests from publication. Never add real keys,
tokens, document content or student information to tracked files.

```sh
curl --fail http://localhost:7071/api/health
curl -i http://localhost:7071/api/v1/auth-check
```

Expected results: `200 {"status":"ok"}` and `401 {"error":"unauthorized"}`.
Health is **liveness only**: reaching the handler proves the process is serving
HTTP, not that storage, authentication or generation is ready. It returns no
configuration, user identity or request content.

## Authentication boundary

`GET /api/v1/auth-check` is a minimal authenticated route example, not a job API.
Azure trigger auth is `ANONYMOUS` because Function keys are not user identity;
the `require_auth` application wrapper performs the actual bearer validation
locally and in Azure. Future private handlers must use the same wrapper.
There is no local authentication bypass and no trust in `X-MS-CLIENT-PRINCIPAL*`
or caller-supplied user headers.

Configure these **public, deployment-controlled** settings in untracked local
settings or future Azure app configuration:

| Setting | Meaning |
| --- | --- |
| `AUTH_ISSUER` | Exact HTTPS issuer of API access tokens, including any trailing slash |
| `AUTH_AUDIENCE` | Intended API audience, not the add-on's public-client ID |
| `AUTH_JWKS_URL` | Fixed HTTPS signing-key endpoint published by that issuer |

This foundation supports **RS256 JWT access tokens** only. It validates the
signature, exact issuer, API audience, expiration, issued-at and not-before (when
present), and a nonempty subject. Expiration, issued-at, issuer, audience and
subject are required; zero clock leeway is used. The user identity is the
`(issuer, subject)` pair, not a display name or header. Providers with another
algorithm or token format require an explicitly reviewed extension.

The fixed JWKS client uses a five-second network timeout and five-minute key-set
cache, refreshing for an unknown key. It never follows token-supplied key URLs.
Missing/malformed/invalid tokens return 401 with a Bearer challenge; absent or
insecure provider configuration and unavailable/empty signing keys return content-free
503 `authentication_unavailable`. Configuration/outage errors are logged as
fixed operational messages, never tokens or exception details.

The deployment must select and restrict its issuer/tenant, API registration,
allowed users and access permissions. Browser OAuth authorization code with
PKCE and protected refresh storage belong to the add-on. A valid principal does
**not** yet authorize upload/job/artifact access: dependent issues must enforce
operation permissions, user-scoped ownership and atomic quotas. Do not expose
this foundation as a production generation service.

## Queue boundary and remaining work

`generation_worker` binds to `generation-jobs` through `AzureWebJobsStorage`.
It intentionally raises `ProcessingUnavailable` for **every** message, without
reading or logging the payload. No HTTP handler enqueues or generates anything.
Do not send real jobs until #8 supplies an accepted processor and payload design.

Azure Queue delivery is at least once. The host configuration sets three maximum
dequeues, a one-minute retry visibility delay, and base64 message encoding.
After exhausted attempts the host moves the message to
`generation-jobs-poison`; this foundation does not consume/delete poison messages
or claim a completed job. Preserve and inspect synthetic failures manually.
Do not put raw study content in queues, including poison queues.

Future #7/#8/#18/#21 must add narrow upload grants, atomic per-user capacity
reservations, private temporary storage, authenticated idempotent deletion,
expiry/tombstone checks before redelivery writes, and conditional stage ownership.
Their retention maximums remain: abandoned/failed uploads 24h; originals and
extraction-only intermediates deleted on processing completion; review results
and images seven days; imported backend payloads/media deleted within 24h of
Anki commit; content-free status/usage 30 days. Minimal dedupe identity lasts
only while its deck mapping exists. None of these dependent behaviors is claimed
implemented here.

## Verification boundary

Offline tests cover route registration, content-free health, bearer claims and
signature failures, forged identity headers, missing provider configuration,
JWKS outage and repeated unavailable-worker delivery. SDK binding discovery is
not a real host startup test. Functions Core Tools/Azurite were unavailable in
the implementation environment, so local HTTP and queue/poison smoke tests were
not run. No Azure resources, region/runtime subscription check, real identity
provider or cloud smoke test were available or authorized. A future authorized
smoke test must confirm host startup, the two HTTP responses above, a valid API
token, synthetic queue retries/poison placement, and content-free diagnostics.

## Temporary storage and retention integration (#18)

[Blob storage](blob-storage.md) adds private user-scoped SDK operations and a
retention-only timer without changing health, authentication or the deliberately
unavailable generation worker. There are still no upload/job HTTP endpoints.
The existing scoped storage requirements feed the backend dependency include.

`retention_worker` binds to `%RETENTION_SCHEDULE%`, with host monitoring and no
startup execution. The local example sets `AzureWebJobs.retention_worker.Disabled`
to `true`; empty inventory/configuration fails explicitly if invoked. No timer
or service was enabled by this implementation. Operator configuration includes
the complete bounded `RETENTION_USERS` inventory and Table/Blob/ARM settings
documented in the Blob contract. SDK policy reads require scoped management
read rights as well as Blob/Table data rights; they never provision resources.

The timer performs bounded conditional physical cleanup, persists continuation
and raises content-free failure for outages, pending drain or missed cycles.
Provisioned monitoring, actual host/managed identity/policy validation and live
physical-retention evidence remain release gates. The former foundation-only
paragraphs above describe #6, not a certification that these new gates passed.
