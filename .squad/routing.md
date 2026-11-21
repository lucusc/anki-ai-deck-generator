# Work Routing

## Routing Table

| Work Type | Route To | Examples |
|-----------|----------|----------|
| Architecture and coordination | lead | API/payload contracts, identity-provider and licensing decisions, dependency gates |
| Python Azure Functions | functions | Authenticated HTTP/queue workers, Blob/Table, quotas, expiry, observability, Bicep |
| Python Anki add-on | addon | Browser PKCE, protected credential storage, responsive UI, review/import, media compatibility |
| Extraction and generation | pipeline | Native parsers, bounded OCR, prompts, deterministic validation/dedupe, diagrams/masks |
| Testing and independent review | tester | Synthetic fixtures, boundary/concurrency/auth/expiry tests, saved Anki rendering, release matrix |

## Work Type → Agent

| Work Type | Primary | Secondary |
|-----------|---------|-----------|
| Architecture | lead | tester |
| Backend and infrastructure | functions | tester |
| Anki desktop | addon | tester |
| Extraction and generation | pipeline | tester |
| Verification | tester | lead |

## Issue Routing

`backlog.md` records each issue's domain route and exact direct prerequisites.
Routes are not active ownership claims. No `squad:*` labels or GitHub assignees
are applied by this setup. Label/comment/assignment writes require separate
authorization; reading issues is safe.

## Rules

1. The parent coordinator claims one accountable owner before dispatch, recording issue, session, branch, file scope, and prerequisite evidence in the canonical orchestration log.
2. Start only work whose actual prerequisites are integrated and verified. Wave membership is not a barrier to unrelated ready work and is not authorization to start.
3. Parallelize only independent work with disjoint write scopes. Shared contracts are agreed by lead first; tester can prepare independent fixtures while implementation proceeds.
4. Escalate unmatched work and ownership conflicts to lead. Do not fan out automatically, spawn anticipatory implementation, or react to all open issues.
5. Scribe consolidation is a bounded clerical task, not a mandatory background agent. Ralph stays idle unless separately authorized for a specific read-only check.
6. Follow `governance.md` over generated examples of automatic GitHub writes, branch creation, deployment, or watcher execution.
