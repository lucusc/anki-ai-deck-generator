### 2026-11-21: Leased conditional temporary artifacts, not write SAS

**By:** functions
**What:** Issue 18 uses the accepted issuer/subject partition and opaque Blob
locator, a fenced artifact inventory in the existing physical Table, immutable
single-PUT payloads, leased placeholders and concrete Blob If-Match. Clients
receive only authenticated, single-blob, five-minute read SAS. Future upload
code must mediate bytes through authenticated server code, not issue write SAS.
Physical leased deletion removes a winning earlier PUT and prevents a later
leased/conditional PUT from recreating the missing blob. Table finalization
refuses pending artifact rows.
**Why:** A Table precheck cannot revoke a SAS or stop an in-flight PUT. Azure
documents write timeouts as ten minutes per MiB, so elapsed client timeout is
not drain proof. Content writes require a pre-existing leased placeholder;
initialization sends zero content and automatic SDK retries are disabled.

An ambiguous initializer or lost initialization acknowledgement remains a
tracked safety blocker until explicitly settled. No automatic unknown-initializer
recovery or exact cross-service atomicity is claimed. Real streaming-write/
deletion semantics need live Azure verification before release.

The production policy reader uses ARM StorageManagementClient because the Blob
data-plane SDK omits versioning/restore settings. Scoped management read rights
are needed in addition to Blob/Table data and delegation-key permissions.
Private/no-Shared-Key/non-HNS storage and disabled retained copies are required.
No provisioning/account-write rights are added.

An inert retention-only timer uses a deployment-controlled inventory of one to
five exact issuer/subject pairs, ten-row user pages and durable continuations,
one-hour cleanup lead, a 180-second application budget and a fifteen-minute
cycle alarm. Failed records/users remain explicit while other cleanup proceeds.
It does not discover all users or scan the account. Actual monitoring, complete
inventory, host/cloud/RBAC smoke, unknown-initializer settlement and consumer
completion/partial-import/media integration remain acceptance gates for 18/21.
Local originals and imported Anki media are never deleted.
