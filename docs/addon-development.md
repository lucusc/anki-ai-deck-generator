# Anki add-on foundation (#1)

The foundation provides a Tools menu entry, modeless browser sign-in, token
refresh and local sign-out. It does **not** upload documents, select decks or
audiences, generate notes, or write to the collection. Those are separate issues.
Squad remains development tooling, not a runtime dependency.

## Desktop version targets and evidence

The explicitly selected compatibility targets are **Anki 25.09 and 26.09.4,
Qt6 desktop**. Other versions are rejected with an actionable warning, rather
than silently claiming compatibility. Do not infer support for Qt5, AnkiMobile,
AnkiDroid, beta releases or other desktop versions.

| Evidence | Status |
| --- | --- |
| Public Tools menu API, `QAction`, `qconnect`, `mw.form.menuTools` | Official add-on guide and upstream source inspected |
| `QueryOp(...).without_collection().failure(...).run_in_background()` | Present in both selected tags; dispatches network work off the GUI/collection executor and completion back to main |
| Packaged entry point/menu, configuration failures, modeless lifecycle, background dispatch, profile cancellation | Automated API-double smoke tests for both version labels |
| Actual installed Anki, Qt event loop, clean-profile restart and OS credential round trips | **Not performed; release gate remains open** |
| Deployed identity provider/API audience, real consent/refresh/revocation | **Not performed; no deployment or credentials supplied** |

Sources inspected 2026-11-21 UTC:
[official menu guide](https://docs.ankiweb.net/addons/a-basic-addon),
[25.09 QueryOp](https://github.com/ankitects/anki/blob/25.09/qt/aqt/operations/__init__.py),
[26.09.4 QueryOp](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/operations/__init__.py),
[25.09 task manager](https://github.com/ankitects/anki/blob/25.09/qt/aqt/taskman.py),
[26.09.4 task manager](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/taskman.py).
26.09.4 was a published stable release; 26.11b1 was a beta, not selected.
API-double tests are not real-application compatibility certification.

## Contributor setup

The runtime uses only Python's standard library and Anki's provided Qt APIs.
No third-party pip packages or backend keys are required. Use Python 3.10+
for local tests; the development run used Python 3.14.0 on macOS. Real target
Anki builds use their own bundled Python; test those separately before release.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s addon/tests -v
python3 addon/tools/build.py /tmp/anki-ai-deck-generator.ankiaddon
```

The builder creates a local zip containing only the entry point, deployment
configuration defaults, manifest, models, services and UI. It excludes tests,
tooling, private files and caches. It neither installs nor deploys anything.
In a **disposable Anki profile**, use Tools > Add-ons > Install from file,
select the archive and restart Anki. Do not install development copies over
another session's work or use private study materials for smoke tests.

Layout:

| Path | Responsibility |
| --- | --- |
| `addon/__init__.py`, `ui/bootstrap.py` | Anki entry point, single Tools action, version/startup errors, profile cleanup |
| `addon/ui/signin.py` | Modeless sign-in/resume/sign-out, main-thread UI callbacks and cancellation |
| `addon/models/auth.py` | Validated public configuration, fixed safe errors, redacted in-memory tokens |
| `addon/services/oauth.py` | Deterministic browser code + PKCE, expiry, serialized refresh and rotation |
| `addon/services/callback.py` | Bounded state-bound IPv4 loopback callback |
| `addon/services/credentials.py` | Explicit native protected credential stores |
| `addon/services/http.py`, `privacy.py` | TLS JSON/form transport, bounded responses, content-free events |
| `addon/tests/`, `tools/build.py` | Synthetic behavior/load tests and local packaging |

## Deployment-configured identity (public values only)

An operator chooses an **OIDC-discoverable OAuth provider** supporting native
public clients, authorization code, S256 PKCE, refresh tokens, and an RFC 8252
IPv4 loopback redirect with an ephemeral port. There is no hardcoded provider,
client secret, API key, Function key, Azure credential or storage key.

Set Tools > Add-ons > Config with the exact deployed values:

```json
{
  "issuer": "https://identity.example.test/tenant",
  "client_id": "public-native-client-id",
  "audience": "https://api.example.test",
  "scopes": ["openid", "offline_access", "study.read"]
}
```

These are **synthetic examples**, not an operational deployment or an accepted
backend payload contract. The default empty values intentionally disable sign-in.
Unknown keys (including secrets), insecure issuer URLs, missing audience,
duplicate scopes and scope sets lacking an API scope or `offline_access` fail
explicitly. Never put credentials in add-on config or commit operational tokens.

Register `http://127.0.0.1:<ephemeral-port>/oauth/callback` according to the
provider's native-client loopback rules. The port is chosen by the OS; it is not
a fixed development port. A provider requiring a fixed-port/web-client secret
is not compatible with this implementation. Restrict approved accounts/tenants
in deployment; a public client ID is not authorization.

Discovery comes from `<issuer>/.well-known/openid-configuration` and must
return the exact configured issuer, HTTPS authorization/token endpoints and
advertised S256 support. Endpoints with preexisting queries are rejected.
The authorization request sends the configured `audience` and scopes; configure
the provider's API resource/scope mapping accordingly. Providers such as Entra
may select audiences using API scopes instead of that parameter: the operator
must verify the **issued access token's audience at the deployed API**. Discovery
alone does not guarantee a particular provider registration is compatible.
The add-on does not treat ID tokens as API authorization or locally claim that
an access token's signature/audience was verified. Backend validation belongs
to its tracked implementation.

Parent-accepted #6 boundary: the API validates **RS256** access-token signatures
using its deployment-controlled `AUTH_JWKS_URL`, exact `AUTH_ISSUER`,
`AUTH_AUDIENCE` and token lifetime; user identity is `(issuer, subject)`. Match
the add-on issuer/audience and issued token algorithm to that deployed boundary.
The JWKS setting belongs on the server, not in this add-on's config.
`/api/health` is public operational health; `/api/v1/auth-check` is an
authenticated sample for manual verification. Neither defines upload/job
payloads or makes the add-on foundation a working generation application.

No automatic retry of authorization-code exchange or refresh occurs: a retry
after an ambiguous network failure can conflict with one-use codes/rotating
refresh tokens. Failures stay explicit; users can sign in again.

## Privacy, credentials and responsiveness

- Browser authentication uses fresh random state and a fresh 86-character
  verifier with S256, never an embedded password form. Code/verifier/refresh
  credentials are sent only to the discovered HTTPS token endpoint; HTTP
  redirects are not followed. Requests time out after 15 seconds and JSON
  responses are capped at 128 KiB.
- The callback binds **only 127.0.0.1**, verifies Host/path, one state/code/error,
  and issuer when advertised (always checks a returned issuer). Bad callbacks
  do not consume the pending transaction. It stops after success, cancellation
  or 180 seconds. Individual loopback sockets have a 0.5-second read timeout.
  Responses are generic, no-store and contain no codes or tokens.
- Refresh credentials use macOS **Keychain Services**, Windows **Credential
  Manager** (generic credential, local OS-user protection), or Linux
  **Secret Service** via `/usr/bin/secret-tool` (`libsecret-tools` on common
  distributions). Linux requires a running, unlocked Secret Service and user
  D-Bus session. Credentials go to stdin, not process arguments. Locked,
  absent or failing stores cause an explicit error; there is no file fallback.
- Windows generic credential blobs are limited to 2560 bytes. Larger refresh
  tokens fail explicitly without accepting an in-memory signed-in session.
  Choose/test an appropriate provider token size rather than weakening storage.
- Credential accounts are SHA-256 of deployment issuer/client/audience/scopes
  and Anki profile name, under service `anki-ai-deck-generator.oauth`. Different
  profiles/deployments do not accidentally resume one another. This permits
  one signed-in OAuth identity per profile/deployment. Sign out **before**
  changing configuration or renaming/deleting a profile; otherwise remove the
  orphaned service item using the OS credential-store UI.
- Access tokens are memory-only, redacted in model representations, and expire
  30 seconds early. Refreshes are serialized per session; rotation is saved to
  the protected store before a session is accepted. Denied refresh removes
  the rejected credential; transient network failures leave it for explicit
  retry. Local sign-out clears memory and deletes the saved refresh credential.
  It does not revoke the provider grant or sign out the browser; revoke at the
  provider if needed.
- Network and store operations run in Anki `QueryOp.without_collection()`.
  The dialog is modeless; callbacks alone update Qt on the main thread.
  Cancel/Close and profile close cancel pending authentication and clear memory;
  late callbacks never update a closed dialog or accept a new memory session.
  In-flight HTTPS calls and Linux store calls finish at their bounded timeout,
  not instantaneously. Native Keychain/Windows calls can wait on OS policy or
  an OS authorization prompt; resolve that prompt in the OS UI.
  If cancellation happens during a store write, the newly saved item is removed;
  a removal failure is reported as a credential error, never silent success.
- The add-on emits only a fixed event/error code through Anki's logging
  infrastructure. It creates no private log files, telemetry exporter or
  extra retention store. No URLs, tokens, raw exceptions, response bodies,
  profile names, document text or study metadata are logged. Startup/UI
  boundaries sanitize unexpected failures instead of dumping tracebacks.

## Required manual smoke matrix (not yet performed)

For each selected Anki version on macOS, Windows and Linux:

1. Install the built artifact in a clean synthetic profile and restart. Verify
   one Tools entry, an actionable unconfigured error, and no startup network or
   credential prompt. Unsupported desktop versions must show the warning.
2. Configure a real approved public client/API scope. Sign in in the default
   system browser, verify consent/account restrictions and PKCE at the provider,
   and keep Anki's normal UI usable throughout. Cancel, deny, time out and test
   blocked networking; no success message should appear for failures.
3. Inspect the OS store for the service item. Confirm no tokens in config, add-on
   files or Anki logs. Close/reopen the dialog or restart Anki, use saved sign-in,
   observe refresh rotation/expiry, and test another synthetic profile's isolation.
4. Lock/unavailable-store tests must fail visibly without fallback. Sign out
   locally and verify item deletion. Test profile switching/closing while an
   authorization request, refresh or protected write is in flight.
5. Verify issuer/RS256 signature/audience/scope/lifetime at the real API with
   the returned access token, deny another tenant/user, and test provider revocation. Record version,
   platform, provider registration, pass/fail and content-free error codes only.

Actual desktop/OS-store and deployed-provider runs are missing environment
evidence, not passing tests. This foundation alone must not close issue #1 or
certify V1 readiness.
