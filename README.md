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
