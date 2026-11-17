# Product Requirements: Anki AI Deck Generator

## 1. Purpose and release scope

Build a family-scale study tool for 1-5 users processing a few documents per week. Transform study documents into high-quality, source-linked Anki notes while minimizing unnecessary AI calls and idle infrastructure costs.

V1 explicitly includes image occlusion generation, promoted from the original V2 proposal. A release is not V1-complete until image occlusion extraction, editable mask review, compatible note generation, and import are verified.

This is a requirements baseline, not a claim that the features are implemented.

## 2. Users and primary workflow

Audiences: Middle School, High School, University, Certification, Professional. Example subjects include biology, history, mathematics, networking, AZ-104, and AZ-305.

1. Select one or more local documents inside Anki.
2. Select an existing deck or create a new deck.
3. Choose audience, optional subject/chapter/tags, card limit, and permitted paid extraction features.
4. Submit a job and receive an identifier without waiting for generation to finish.
5. View extraction and generation progress, failures, and estimated usage.
6. Review generated text notes and diagram masks; edit, exclude, or approve them.
7. Insert approved notes and required media into the selected Anki collection.
8. See counts for processed/failed files, proposed/imported notes, generated cards, rejected notes, and duplicate skips.

## 3. Functional requirements

### FR-01: Anki desktop add-on

- Provide a Tools menu entry and a non-blocking upload/review workflow.
- Support PDF, DOCX, PPTX, TXT, and MD files; reject unsupported files with actionable errors.
- Validate file size, file count, and content type server-side as well as client-side.
- List existing decks, support deck creation, and keep collection writes on supported Anki APIs.
- Declare and test supported Anki desktop versions before release.

### FR-02: Job API and lifecycle

- Authenticate upload, job status, results, and deletion operations; isolate each user's sources and results.
- Accept deck identity, audience, optional subject/chapter/tags, and generation settings.
- Return HTTP 202 and a job identifier for accepted asynchronous work.
- Expose queued, extracting, generating, ready_for_review, completed, and failed states. Completed means the client has acknowledged import; result availability alone is ready_for_review.
- Track per-document outcomes so a failed file is not silently reported as successful.
- Support retry-safe submissions, bounded processing attempts, poison-message handling, and actionable error codes.

### FR-03: Native extraction first

- Extract digital PDF text with page references using a license-compatible parser selected before distribution.
- Extract DOCX paragraphs/tables, PPTX slide text and speaker notes, and UTF-8 TXT/MD.
- Preserve page/slide/section references and maintain extraction order where available.
- Detect empty or insufficient extraction using a documented, fixture-tested rule; do not generate plausible cards from missing content.
- Treat unsupported, encrypted, corrupt, and image-only inputs explicitly.

### FR-04: Metered extraction fallback

- Allow Azure AI Document Intelligence only when native extraction is insufficient or image label detection requires it.
- Require explicit configuration/consent for paid fallback and show the reason for using it.
- Enforce page and spending-related request limits before dispatching paid work.
- When fallback is disabled, return an actionable per-document outcome instead of silently omitting content.

### FR-05: Card generation and quality

- Use a deterministic extraction -> chunking -> generation -> validation -> merge pipeline, not an autonomous agent.
- Bound chunk size, overlap, model output, and total notes. Default to at most 25 proposed notes per chapter; when chapter boundaries are unknown, use one document as the chapter unit.
- Distinguish notes from rendered Anki cards: a reversed note or multiple cloze deletions can create several cards. Display both counts and enforce separately configured card limits.
- Generate Basic, Basic and reversed, and Cloze notes. Comparison, Scenario, and Process are pedagogical formats mapped to supported note models, not assumed built-in Anki types.
- Adapt language and complexity to audience while preserving source meaning.
- Keep prompts versioned outside runtime logic and request schema-valid structured output.
- Require atomic, unambiguous questions; reject malformed cloze syntax, unsupported facts, missing answers, excessive length, and repeated concepts according to documented validation rules.
- Never silently repair a failed model response into a success. Bound retries and retain an actionable failure.
- Every proposed note must include source attribution and be reviewable before import.

### FR-06: Incremental processing and duplicates

- Compute SHA-256 from original file bytes before generation.
- Scope source reuse by user, source hash, extraction/generation version, audience, and relevant settings. Changing audience or prompt version must not return an incompatible cached result.
- Reuse successful compatible results; failed/incomplete jobs remain retryable. Duplicate uploads must not cause duplicate billable generation through concurrent requests.
- Use deterministic normalization and hashes for exact duplicate notes/concepts. Do not claim semantic equivalence detection from hashes alone.
- Scope note deduplication to the intended user/deck and document its behavior for reversed and cloze variants.
- Recheck imported note identity in Anki so repeated import, client retries, or a backend acknowledgement failure cannot insert duplicate notes.
- Do not mark a note imported before Anki has committed it.

### FR-07: Storage and source traceability

- Blob Storage: original documents, extracted artifacts/diagrams, and immutable result payloads.
- Table Storage: Documents, Cards, Decks, and Jobs. Define partition/row keys and lookup indexes around actual access patterns.
- Track deck, subject, chapter, source hash, card hash, created date, source location, prompt/model versions, and processing status.
- Preserve source references in Anki note fields or a documented compatible metadata mechanism.
- Provide configurable retention and authenticated deletion of sources, extracted artifacts, and results; disclose any retained deduplication metadata.

### FR-08: Image occlusion (required in V1)

- Extract diagram images from PDF, DOCX, and PPTX, including rendered page/slide regions when labels are separate from embedded images.
- Detect candidate labeled diagrams such as cells, maps, charts, and architecture diagrams. Explain when no suitable diagrams are found.
- Generate proposed rectangular or polygonal masks from label regions with image dimensions, coordinate system, and confidence metadata.
- Uncertain masks require review; never automatically approve masks based solely on a model response.
- Provide an image preview where users can add, edit, remove, include/exclude, and approve masks.
- Preserve image aspect ratio, ensure masks stay within image bounds, and keep question/answer label behavior consistent.
- Support an explicitly selected and documented Anki image occlusion target. Investigate native Anki Image Occlusion versus Image Occlusion Enhanced; they are not interchangeable schemas.
- Include a tested Image Occlusion Enhanced compatibility path as proposed in the backlog, documenting any required add-on and supported versions. Do not write undocumented collection internals.
- Copy media safely into Anki, use collision-resistant names, and preserve media/mask identity across retries.
- Verify saved notes render correctly in question and answer views after closing and reopening Anki. Track proposed masks, notes, and rendered cards separately.

### FR-09: Review and import

- Show editable note content, audience, tags, source, validation warnings, and duplicate status.
- Import only approved notes; no collection writes merely because generation completed.
- Map fields to supported note models without overwriting user-customized models.
- Sanitize generated markup, disallow executable content, and escape untrusted names and metadata.
- Report partial import failures and allow safe retry without losing successful imports.

### FR-10: Operations and cost control

- Record job duration, extraction method, input/output token usage, model/deployment, retry counts, and estimated cost.
- Label estimates and their pricing assumptions; distinguish them from Azure billing totals.
- Configure per-job document/page/note/card/token limits, bounded retries, and upload concurrency.
- Provide Azure budget alerts and documented manual spending controls; alerts alone are not a hard spending cap.
- Avoid logging document text, prompts, model output, credentials, or personal study metadata.

## 4. Architecture and nonfunctional requirements

- Python Azure Functions on a region/runtime-compatible Consumption option with scale-to-zero behavior; choose the currently supported SKU during implementation.
- Use Blob, Queue, and Table Storage rather than Cosmos DB or Service Bus.
- Use an available pay-per-use Azure OpenAI deployment; avoid provisioned throughput for this workload.
- No always-on application compute. Storage, telemetry, secrets, and AI resources can still incur charges while Functions are idle.
- Upload via authenticated, short-lived, narrowly scoped access; use managed identity and least privilege between Azure resources wherever supported.
- Enforce authorization on every job/artifact operation; possession of a job ID is not authorization.
- Treat uploaded material as untrusted data, not prompt instructions. Bound parser resources and handle zip-based document expansion safely.
- Keep long-running work off HTTP request lifetimes. Split or checkpoint work to remain within the selected Functions plan's execution limits.
- Use Azure Queue at-least-once delivery with leases/conditional writes and idempotent stages; do not claim exactly-once execution.
- Keep UI responsive during network work; show explicit network and backend errors.
- Measure stage timings and representative workload costs before setting performance or monthly-budget claims.
- Use synthetic/openly licensed fixtures for digital PDF, scanned PDF, DOCX, PPTX, TXT, MD, diagram images, and corrupt input.

## 5. V1 release acceptance

- An end-to-end supported-format matrix demonstrates extraction, generation, human review, and Anki import with source references.
- Basic, reversed, cloze, and image occlusion notes render correctly on declared supported desktop versions.
- A labeled diagram produces editable masks and a functioning saved question/answer card with intact media.
- Repeated uploads, concurrent identical jobs, queue redelivery, and repeated imports do not create duplicate generation or notes under the documented recovery model.
- Tests cover insufficient extraction, disabled OCR, authorization failures, generation failure, poison messages, malformed output, and partial import recovery.
- Note/card/page/token limits are enforced at their real boundaries, not only mentioned in prompts.
- Bicep deployment and GitHub Actions use no committed secrets; resource cleanup and cost-control instructions are documented.
- Telemetry contains operational identifiers and counts, not private document contents.

## 6. Out of scope for V1

- APKG export and deck sharing.
- Dedicated exam-focused/learning-focused modes and explicit regenerate-from-source controls.
- Cross-chapter midterm reviews, knowledge graphs, personalized weak-area decks, Foundry Agents, and AI Search.
- Cloud synchronization of Anki collections or replacement of Anki's scheduler.

## 7. Implementation decisions to resolve in tracked issues

- Authentication model suitable for a small private user group.
- Python Functions SKU/runtime/region and available pay-per-use model.
- PDF parser licensing and diagram rendering approach.
- Supported Anki versions and exact image occlusion compatibility mechanism.
- Document limits, native-extraction quality thresholds, retention defaults, and pricing assumptions based on measured fixtures.
