# Architecture

## V1 flow

```text
Anki desktop add-on
  -> authenticated HTTP Functions (upload authorization / job / status / result)
  -> private Blob Storage (documents)
  -> Queue Storage (job references only)
  -> Python queue-triggered Functions
       -> native extraction
       -> optional metered OCR / label detection
       -> bounded chunks + Azure OpenAI structured generation
       -> validation + deterministic duplicate checks
       -> diagram masks + media artifacts
  -> private result Blob + Table job status
  -> Anki review UI
  -> approved collection/media import + acknowledgement
```

HTTP requests enqueue work and return 202; they do not wait for document generation. Workers split/checkpoint large work to respect the chosen plan's execution limits.

## Decisions

1. **Consumption Functions:** intermittent use should not require always-on application compute. Validate supported runtime/SKU/region and workload limits before provisioning.
2. **Table Storage:** user/deck/source-hash/card-hash lookups do not initially justify Cosmos DB. Design explicit keys/indexes; avoid unbounded scans.
3. **Thin Anki client:** local deck selection, preview, approval, and collection writes; cloud extraction/generation.
4. **Native extraction first:** DOCX/PPTX/TXT/MD and digital PDF parsing precede any paid OCR. Review PDF parser licensing.
5. **Queues from V1:** at-least-once work delivery, bounded retry, poison handling, and conditional state transitions instead of fragile long HTTP requests.
6. **No agents:** the initial workflow is deterministic. Prompts and model schemas are versioned.
7. **Image occlusion in V1:** include extraction, label localization, editable masks, media, and tested Anki compatibility; do not equate native occlusion with Image Occlusion Enhanced.

## Data responsibilities

| Store | Contents and lookup |
| --- | --- |
| Documents | User-scoped source SHA-256, extraction version, source metadata, Blob references, state |
| Cards | User/deck-scoped normalized hashes, generated note payload references, source/model/prompt provenance, import identity |
| Decks | User-scoped logical deck mapping and subject/chapter metadata |
| Jobs | User-scoped request settings fingerprint, lifecycle, per-file outcomes, usage, result reference, concurrency state |
| Blob Storage | Originals, extracted text/images, result JSON, reviewed media artifacts with configurable retention |
| Queue Storage | Small job/stage references; no raw document content |

Define final partition/row keys, conditional updates, and any lookup entities in implementation issues. No cross-table transaction is assumed.

## Consistency and recovery

- Cache identity includes user, source bytes, audience, relevant settings, and pipeline versions.
- Workers acquire conditional ownership and persist stage checkpoints; ownership expiry is recoverable.
- At-least-once queue delivery must not imply repeated AI calls after a successful recorded stage.
- A crash between an external AI response and persisting it may make exact billable-call deduplication impossible; document this boundary and bound recovery retries.
- Result-ready and client-import-completed are separate states.
- The client uses persistent generated-note identifiers to recover from failed acknowledgements without duplicate insertion.

## Security, operations, and deployment

Use private containers, authenticated API access, user-scoped authorization, short-lived upload/result access, and managed identity for Azure access where supported. API keys or Function keys embedded in a public add-on are not a complete user authentication model.

Keep documents and model output out of telemetry. Treat source text as untrusted prompt data and sanitize note HTML. Bound uploads, decompression, parsing, page rendering, tokens, retries, and concurrency.

Bicep is the initial infrastructure source of truth; Terraform is not required in parallel. GitHub Actions should use Azure OIDC rather than stored publish profiles. Application Insights sampling and retention must be configured for low-volume cost control.

Cost estimates must state region/model/pricing date and include OCR, model tokens, storage operations, and telemetry. No fixed monthly cost is asserted. Budget alerts notify; they do not stop all spending.
