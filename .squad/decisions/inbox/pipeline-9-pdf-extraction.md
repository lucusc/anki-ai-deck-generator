### 2026-11-21: PDF parser, resource boundary and proposed extraction contract

**By:** pipeline, assigned issue #9.

**What:** Use BSD-3-Clause `pypdf==7.1.1`, not AGPL/commercial PyMuPDF. Preserve
`backend/extraction/THIRD_PARTY_NOTICES.txt` in distribution. Parent must include
the scoped runtime manifest during reconciliation; no backend-root manifest,
Function/auth/worker or sibling storage file was changed.

The proposed PDF-local contract is `PdfExtraction(outcome, pages, page_count,
reason, version="pdf-native-1")` with frozen `PdfPage(page_number, text,
alphanumeric_characters, sufficient, has_image, has_graphics)`. Page indices are
one-based physical pages; text is normalized NFC Unicode in PDF content-stream
order, not a guarantee of arbitrary visual/column reading order. Every page is
retained on complete ok/image-only/insufficient outcomes; hard failures return
no partial content. `reason` is a fixed operational code. These types do not
define sibling-format, job, storage or generation schemas.

Native-text eligibility requires each nonblank page to have >=80 Unicode
alphanumeric characters, >=60% alphanumeric/non-whitespace density and <=2%
replacement/control/format/non-whitespace characters. Blank separators are
neutral; scanned, short-text and vector-only pages cannot be averaged away.
Repeated characters can still pass: this is not semantic quality validation.
All three threshold boundaries, painted-vs-unused raster resources and partial
documents are fixture-tested.

Default limits: input 16 MiB, 100 physical pages, 8 MiB per examined decoded
page/Form content stream, 32 MiB summed examined decoded bytes (repeated Form
invocations count again), 1,000,000 normalized output code points, 32 nested
Forms, 512 MiB child virtual address space, CPU 10 seconds soft/11 hard, wall
15 seconds. Content caps apply after decoding; **Linux hard RLIMIT_AS,
RLIMIT_CPU and parent timeout** enforce prior allocation/CPU boundaries. These
are per-parser limits, not whole-instance limits or per-user atomic quotas.
Non-Linux fails closed. Core dumps and inherited environment are disabled;
source content/diagnostics are not logged or written to parser output files.

Explicit outcomes: ok, unsupported, encrypted, corrupt, image_only,
insufficient_text, resource_limit, isolation_unavailable, parser_unavailable,
parser_failure. Parser warnings become corrupt, not repaired success. pypdf's
native LimitReachedError becomes resource_limit. Abrupt SIGKILL/memory exits
have an explicitly ambiguous `process_memory_or_termination` reason.

Disable the optional JBIG2 external decoder through supported pypdf
configuration, including legacy overrides: native text must not spawn decoder
children or create image temporary files. A pinned private
`PdfReader._handle_encryption` override aborts on the parsed encrypted trailer
before empty-password auto-verification; this recognizes genuine RC4/AES inputs
without a runtime crypto provider. Upgrade tests must protect this deliberate
private-hook dependency.

**Why:** Satisfy the live #9 criteria without assuming AGPL acceptance, purchasing
a license, falling back to in-process parsing, interpreting input as commands,
or silently allowing good text to hide missing pages. Actual Linux parser
fixtures prove CPU, memory, wall and native decompression limits; ten weakened
implementation copies were rejected by the critical contract assertions.

**Integration/release boundaries:** Parent/lead must review this proposed
contract and dependency include before sibling issues use it. OCR consent/
dispatch remains #13; source hashes, temporary persistence, deletion and quotas
remain their assigned issues. Real Functions-host/Azure OS-limit behavior,
concurrency headroom and real-document reading fidelity/performance are not
verified or claimed. See `docs/pdf-extraction.md` and the committed handoff.

### 2026-11-21: User-directed self-contained PR integration

**By:** pipeline, coordinator-authorized scope extension after bootstrap PR #49.

**What:** Merged `origin/main` at `22258947c0fb0e6ed98b2866b94511492db6cbee`.
Resolved the stale #21 backlog row using main's accepted canonical state; no
other-member/canonical delta remains in the issue PR. Root `requirements.txt`
now includes `extraction/requirements.txt`, and root pytest discovery includes
`extraction/tests`, preserving existing foundation/storage includes.

All current PDF tests/docs use the deployed `backend/` module root and
`extraction` imports, not a second `backend.extraction` package identity.
The isolated parser supports the fixed deployment-owned
`.python_packages/lib/site-packages` directory after installing OS limits;
no inherited Python path or secret environment is introduced. A clean
interpreter fixture exercises the actual parser from that Functions packaging
layout without a globally installed parser.

**Why:** The user requested GitHub PR/serial-main integration, and the
coordinator explicitly released these root tooling paths to #9 so the PR is
self-contained. The default backend-root suite now verifies the integration:
Linux CPython 3.13.18 **130 passed / 1 skipped**; macOS CPython 3.13.9
**125 passed / 6 skipped**. All original ten weakened contract copies are still
rejected. Real Functions-host/Azure and fidelity/concurrency gates remain open.
