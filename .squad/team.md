# Squad Team

> Anki AI Deck Generator: development coordination, not application runtime agents.

## Coordinator

| Name | Role | Notes |
|------|------|-------|
| Squad | Coordinator | Copilot app parent orchestrates bounded child sessions, ownership, and handoffs. |

## Members

| Name | Role | Charter | Status |
|------|------|---------|--------|
| lead | lead | `.squad/agents/lead/charter.md` | Active |
| functions | Backend Developer | `.squad/agents/functions/charter.md` | Active |
| addon | Python Anki Add-on | `.squad/agents/addon/charter.md` | Active |
| pipeline | Extraction / Generation | `.squad/agents/pipeline/charter.md` | Active |
| tester | Test Engineer | `.squad/agents/tester/charter.md` | Active |

## Built-in Support

Scribe records decisions and handoffs; the coordinator may perform the clerical
file updates without spawning another session. Ralph is idle, with no polling or
automatic assignment enabled. Rai and Fact Checker remain available as upstream
support identities for explicitly requested, bounded reviews.

## Project Context

- **Project:** lucusc/anki-ai-deck-generator
- **Stack:** Python Azure Functions, Python Anki desktop add-on, Blob/Queue/Table Storage, Azure OpenAI.
- **Requirements:** `docs/PRD.md`, `docs/architecture.md`, `docs/roadmap.md`, and all current issue acceptance criteria.
- **State:** local, versioned `.squad/`; see `governance.md` for cross-worktree reconciliation.
- **Queue:** `backlog.md`; the parent records active assignments and acceptance evidence.
- **Preset provenance:** unused default identities are retired in the canonical casting registry, not reused under different roles.
