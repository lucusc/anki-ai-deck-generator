# Anki AI Deck Generator

Generate reviewable Anki notes from PDF, DOCX, PPTX, Markdown, and text study materials using a low-cost Azure backend and a thin Anki desktop add-on.

## Planned V1

- Audience-aware Basic, Basic and reversed, and Cloze notes.
- Incremental deck building with source traceability and duplicate prevention.
- Diagram extraction, editable occlusion masks, and image occlusion notes.
- Native document parsing first; metered OCR only when needed.
- Asynchronous processing, bounded AI usage, and infrastructure that scales down when idle.

This repository currently contains requirements and a tracked implementation backlog, not a working application.

## Documentation

- [Product requirements](docs/PRD.md)
- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Implementation issues](https://github.com/lucusc/anki-ai-deck-generator/issues)

## Architecture

Anki add-on -> HTTP Azure Functions -> Blob / Queue Storage -> queue-triggered Functions -> Azure OpenAI -> result Blob -> reviewed Anki import.

Azure Table Storage tracks jobs, sources, decks, generated notes, and duplicate hashes. Azure AI Document Intelligence is an optional, explicitly enabled extraction fallback.

No Cosmos DB, Foundry Agents, Service Bus, Container Apps, AI Search, or Kubernetes are required for V1.

## Cost and privacy

Designed for 1-5 users and a few documents per week. Actual Azure cost depends on region, model, document volume, OCR use, and telemetry; no monthly price is guaranteed. Uploaded documents and generated study content must never be committed to this public repository.

## Development

Implementation, supported Anki versions, local setup, and deployment instructions will be added through the backlog. Use synthetic or openly licensed fixtures only. Do not commit credentials, private study materials, or student information.

## Squad development coordination

The repository uses [official github/squad](https://github.com/github/squad),
CLI **2.0.0**, with a local, versioned team and no active automation workflows.
Squad coordinates development only; it does not change the deterministic
runtime pipeline or the architecture's **No agents** decision.

Use Node.js 22.5+ and the ephemeral pinned CLI (no global installation required):

```sh
npx --yes @bradygaster/squad-cli@2.0.0 doctor
npx --yes @bradygaster/squad-cli@2.0.0 status
npx --yes @bradygaster/squad-cli@2.0.0 cast
npx --yes @bradygaster/squad-cli@2.0.0 client list
```

The setup was generated with
`init --preset default --no-workflows --no-vscode-default --client copilot --state-backend local`
then customized; **do not rerun init** on an existing team. The CLI's default
preset bootstrap also initialized `~/.squad` automatically; no global executable
was installed. All repository launch commands and MCP wiring are portable and
pinned, with no dependency on that home preset cache.

For Copilot CLI, use `copilot --agent squad`; in VS Code select **Squad**.
`.mcp.json` starts the official `squad_state` bridge via pinned `npx` when the
host loads it. Approve repository MCP configuration using the host's normal
trust controls; do not bypass permissions with `--yolo`.

For **Copilot app child sessions**, read [contributor instructions](AGENTS.md)
and the [ownership/handoff procedure](.squad/governance.md). The parent first
integrates this setup, records one owner/session/branch/write scope before
dispatch, and passes the same team's charter and decisions. Children read/write
their own worktree's local Squad state and return committed handoffs; the parent
serially reconciles decisions, histories, logs and active ownership. State is
not automatically shared or locked across worktrees. A host that does not load
the custom agent/MCP can follow the same files directly; automatic app-host
MCP discovery is not verified by CLI diagnostics.

| Entry point | Purpose |
|-------------|---------|
| [.squad/team.md](.squad/team.md) | Five specialists: lead, functions, addon, pipeline, tester |
| [.squad/routing.md](.squad/routing.md) | Architecture, Python Functions, Anki, extraction/generation and verification ownership |
| [.squad/decisions.md](.squad/decisions.md) | Shared contracts, OAuth/PKCE, quotas, temporary retention and release constraints |
| [.squad/backlog.md](.squad/backlog.md) | Exact Direct prerequisites for all 48 issues; #1 and #6 initially independent |
| [.squad/governance.md](.squad/governance.md) | Parent-owned claims in canonical orchestration logs, child handoffs and conflict resolution |

#1-42 are required for V1, including image occlusion; #43-48 are explicitly
post-V1. The backlog's waves express dependencies, not authorization or a claim
that earlier issues are implemented. GitHub issue bodies remain authoritative.
No watcher, auto-assignment, issue/PR writes, deployment or paid service was
enabled. Upstream workflow templates are inert; review upgrades before retaining
new generated automation or overwritten policies.
