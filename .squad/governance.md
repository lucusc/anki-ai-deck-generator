# Team Ownership and Copilot App Handoffs

## Authority and safety

The live GitHub issue body (including OAuth/temporary-retention additions) and
project docs define acceptance. `.squad/backlog.md` is Squad's canonical offline
queue, not an alternative issue tracker. Team/routing/charters define domain
ownership; decisions capture shared contracts. No issue is complete because a
session ended or a scaffold exists.

The repository uses the official Squad coordinator and state MCP bridge, with
repo-specific restrictions instead of the generated default autonomous routing.
No active `.github/workflows/`, watcher, auto-assignment, deployment or paid
service is installed. Shipped workflow *templates* under `.squad/templates/`
are inert references, not authorization to activate them. Review CLI upgrades
before retaining generated workflows or overwritten governance.

## Child-session entry and ownership

1. The parent must first integrate this setup into its branch and ensure each
   child's checkout contains that commit and the latest accepted contracts.
   App sessions do not automatically share new branch commits or unsaved files.
   Do not run `init` again to create a different team or use the main checkout
   as a shared writable team root.
2. Before dispatch, the parent reads live issue state/Direct prerequisites and
   this backlog. A prerequisite is satisfied only by an integrated, verified
   implementation, not an open sibling session or a local completion claim.
   Record missing prerequisites as blocked. Get lead agreement on shared
   payload/auth/storage contracts before parallel implementation.
3. The parent creates one canonical
   `.squad/orchestration-log/{UTC-timestamp}-{member}-issue-{N}.md` entry using
   `templates/orchestration-log.md`. Include issue number, accountable member,
   child session ID (append when available), assigned branch, exact allowed
   write paths, prerequisite commit/evidence, state `assigned`, and outcome
   `pending`. Record the active session/branch in the backlog row. This parent
   record is the authoritative ownership claim, not a GitHub label or the
   child's stale backlog copy. Do not dispatch a second owner for the same issue.
4. In the kickoff, supply the issue and verbatim scope, charter, accepted
   decision/contract context, ownership record, and the child's own checkout as
   `TEAM_ROOT` / `WORKTREE_PATH`, with `STATE_BACKEND=local`. Give exact read/write
   scope and a bounded stop condition. The child reads `AGENTS.md`, team,
   routing, decisions, backlog, governance, its charter/history and live issue.
   Use the app's child-session mechanism; do not spawn nested teams, pollers,
   or additional sessions unless separately delegated.
5. Each child writes only its local worktree: code within its assigned scope,
   member history, a uniquely named `decisions/inbox/{member}-{issue}-{slug}.md`,
   and an orchestration handoff entry. Return commit SHA/branch, acceptance
   evidence, decisions, changed paths and blockers to the parent. Never edit
   another worktree or treat local state as immediately visible to siblings.
6. The parent serially integrates reviewed child commits and canonical records,
   consolidates the decision inbox, and appends a log event with outcome
   `review`, `blocked`, `released`, or `completed`. Keep earlier claim evidence;
   do not erase/reuse ownership identities. Only the parent updates the
   authoritative backlog's active claim/status. Resolve structured-file
   conflicts semantically; union merges are only suitable for append-only text.
7. Fan out independent ready issues with disjoint scopes; prepare test fixtures
   in parallel only without overlapping writers. The same specialist may serve
   multiple sequential tasks, but each implementation issue has one active
   owner. Synchronize accepted decisions into children before dependent work.

## Explicitly requested GitHub PR integration

When the user explicitly requests GitHub PRs and merging into `main`, use one
issue-scoped PR per implementation child and reviewed serial merges instead of
repeated local cherry-picks. Already accumulated coordinator changes may land
in a clearly described bootstrap PR; do not create duplicate issue PRs for code
already included there.

After the bootstrap merge, children fetch and merge `origin/main` into their
own branches before opening PRs. Preserve their implementation and reconcile
canonical records semantically; never overwrite main with a stale child
backlog. Each handoff includes the real PR URL, head SHA, issue acceptance
evidence and unresolved gates. The coordinator reviews the actual PR delta,
checks required statuses and merges through GitHub without bypassing protection.
Use merge commits when available to preserve shared prerequisite ancestry.
Synchronize the coordinator's feature checkout with merged `origin/main`;
never mutate the main checkout directly.

Use closing issue references only when every acceptance criterion is satisfied.
Merging useful foundation code does not close missing desktop/cloud/retention
verification. Keep those issues open and linked with non-closing references.
Before merging, inspect the PR's live `closingIssuesReferences`. GitHub can
recognize a closing verb followed by an issue number even inside a negated
sentence. For incomplete work use only non-closing links; do not negate a
closing keyword adjacent to an issue reference. Correct accidental auto-closure
caused by this workflow while preserving any independent user closure decision.
This explicit PR workflow does not authorize deployment, paid services,
watchers, generated automation, or unattended Agent merge.

## Persistence and limitations

`stateBackend: local` means branch-local filesystem state. It provides no
distributed locking across Copilot app worktrees; the single parent dispatch
ledger prevents duplicate assignments operationally. This is not a claim of
automatic cross-session exclusion or live state synchronization. Runtime file
tools and the official `squad_state_*` MCP tools address the same local store.

Ownership logs and decision inbox entries are deliberately versioned, unlike
the generated default ignore rules. Raw runtime logs, caches and sessions stay
ignored. Never record credentials, personal materials or private document text.

No automatic PR creation/merge, issue labels/comments/closure or deployments.
Such actions need explicit authorization and review. A completed handoff must
state missing manual Anki/cloud verification plainly; the parent decides release
readiness against all V1 criteria, not just graph completion.
