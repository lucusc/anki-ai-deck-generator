### 2026-11-21: Add-on foundation targets and public OAuth configuration
**By:** addon
**What:** Proposed Anki compatibility targets are Qt6 desktop 25.09 and 26.09.4,
with an explicit unsupported-version warning. Public config consists only of
issuer, client_id, audience and scopes. Use an OIDC-discoverable public native
client with S256, refresh tokens and RFC 8252 ephemeral IPv4 loopback redirect.
Refresh credentials use native Keychain Services, Windows Credential Manager,
or Linux Secret Service; no dependency bundle or file fallback. One credential
account is isolated by deployment configuration and Anki profile name.
**Why:** Stable, independently inspectable desktop tags expose the documented
menu/QueryOp/profile APIs. Deployment configuration must select the actual
provider and align scopes/audience with the parent-accepted #6 RS256 boundary;
no provider credentials or sibling upload/job contracts are invented.

Tests cover packaged loading with API doubles, live synthetic loopback requests,
PKCE wiring, refresh rotation/expiry, cancellation, safe failures and Linux
store commands. macOS CoreFoundation bindings/query/data allocation were
exercised without reading/writing the user's Keychain. Actual Anki/Qt and native
store round trips on all three OSes, real provider registration and deployed API
authorization remain manual release gates, not accepted compatibility claims.

Windows generic credential blobs are bounded at 2560 bytes; deployments with
larger refresh tokens must select a compatible provider/configuration or address
storage in an explicitly assigned follow-up, never downgrade protection.
Configuration/profile renames can orphan old protected entries; sign out first
or remove the service item in the OS UI. Native Keychain/Windows policy prompts
may require OS interaction even after the add-on dialog is cancelled.

Parent reconciliation suggestion: link `docs/addon-development.md` from root
README and distinguish the implemented foundation from the still-unimplemented
document/generation/review/import pipeline. Do not mark #1 complete until real
desktop/provider evidence satisfies the live criteria.
