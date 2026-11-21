# Native PDF extraction

Issue #9 implements reusable deterministic extraction in `backend/extraction/`.
There is no HTTP, Blob, Queue, OCR, image export, chunking or generation
integration. The Functions worker remains unchanged.

## Parser and license decision

Use **pypdf 7.1.1**, pinned in the scoped `requirements.txt`, rather than PyMuPDF.
The [PyMuPDF licensing documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
offers AGPL or commercial licensing. The repository has not adopted AGPL terms
or authorized a commercial purchase; a public repository alone does not resolve
those obligations. This is an engineering dependency choice, not legal advice.

[pypdf 7.1.1's license](https://github.com/py-pdf/pypdf/blob/7.1.1/LICENSE)
is BSD-3-Clause, permits source/binary redistribution with conditions, and
supports Python 3.13. Preserve the bundled
`backend/extraction/THIRD_PARTY_NOTICES.txt` in distributions. Neither MuPDF nor
an external rendering/OCR executable is used. License sources were checked on
2026-11-21. The test-only cryptography dependency generates original AES fixtures;
runtime PDF extraction does not need it.

The standalone parser test manifest pins pytest 9.0.3 and cryptography 50.0.2,
matching the reviewed dependency-remediated test environment. These are test
dependencies, not a new runtime decryption capability.

The backend manifest includes the scoped runtime dependencies, and its default
test runner includes `extraction/tests`. Root tooling changes were explicitly
authorized for the self-contained #9 PR after the bootstrap merged.

## Proposed local contract

Use the Functions app's **`backend/` module root** and import `extraction`,
matching the foundation's `auth` and `storage` namespaces. Do not load the same
files again as `backend.extraction` or `backend.auth`:

```python
from extraction import PdfOutcome, extract_pdf

result = extract_pdf(pdf_bytes)
if result.outcome == PdfOutcome.OK:
    for page in result.pages:
        process_source_text(page.page_number, page.text)
else:
    handle_document_outcome(result.outcome, result.reason)
```

The example callbacks are caller responsibilities, not implemented APIs.
Input must be immutable original `bytes`; hashing/source IDs belong to later
issues. `PdfExtraction` and `PdfPage` are frozen dataclasses:

| Field | Contract |
| --- | --- |
| `outcome` | `PdfOutcome` string enum, below |
| `version` | `pdf-native-1`; change when extraction/quality behavior changes |
| `page_count` | Total pages only after complete extraction; otherwise zero, not an estimate |
| `pages` | Ordered tuple containing every page, including empty/insufficient pages |
| `reason` | Fixed content-free diagnostic code, or `None` for `ok` |
| `page.page_number` | One-based physical PDF page index, not printed page label |
| `page.text` | NFC Unicode; horizontal whitespace collapsed per line, outer whitespace stripped |
| `page.alphanumeric_characters` | Count of Unicode `isalnum()` characters in normalized text |
| `page.sufficient` | Versioned per-page native-text heuristic, not semantic accuracy |
| `page.has_image` | Painted raster XObject or inline image, including inside invoked Forms |
| `page.has_graphics` | Painted vector path or shading, including inside invoked Forms |

Page and text-fragment order follow **PDF content-stream order** via pypdf's
plain extraction mode. Fixture order and line breaks are deterministic. This
does not promise visual reading order for arbitrarily positioned/multicolumn
text, correct mathematical layout, table structure or accessibility-tag order.
Font mapping errors and incomplete text layers remain possible. No instructions,
markup, scripts, links or attachments in the source are executed.

| Outcome | Meaning / caller action |
| --- | --- |
| `ok` | Native text meets the rule on all nonblank pages; eligible for subsequent validation |
| `encrypted` | A parsed trailer marks encryption; request an unencrypted export |
| `corrupt` | Structural parsing failed, or pypdf warned about repair/substitution/skipped content; request a valid export |
| `image_only` | No native text and at least one painted raster image; OCR may be proposed by #13, never called here |
| `insufficient_text` | Empty, short, noisy, vector-only or partially extracted document; do not generate from it silently |
| `unsupported` | Missing leading `%PDF-` header or unsupported native decoding feature |
| `resource_limit` | Input/pages/decoded content/output/depth/native parser/OS limit reached; split or reduce the input |
| `isolation_unavailable` | Non-Linux platform or process/OS-limit setup failure; do not parse in-process as a fallback |
| `parser_unavailable` | Scoped parser dependency is missing; operator must repair installation |
| `parser_failure` | Unexpected child exit or invalid child result; operator must investigate with synthetic reproduction |

Only `ok`, `image_only` and `insufficient_text` retain complete page tuples.
All hard failures discard partial text. These pages are **private source
content**, not telemetry, queue payloads or Table entities. Persistence, consent,
expiry/deletion and atomic per-user quotas remain the caller's tracked issues.

## Native-text sufficiency

A page must have **at least 80 Unicode alphanumeric characters**, at least
**60% alphanumeric characters among non-whitespace characters**, and at most
**2% replacement/control/format characters among non-whitespace characters**.
The latter counts U+FFFD and Unicode general categories starting with `C`.
No English-only word/token count is imposed.

Every page with native text, painted images or painted vector graphics must
meet this rule. Truly empty pages can be neutral separators; an entirely empty
document is insufficient. A good page cannot average away a scanned page,
a short caption/page-number text layer or a vector-only page. Unused image
resources do not make a blank page image-only. Image detection inspects painting
operators/resources without decoding or exporting image pixels.

The conservative threshold supplies roughly a short explanatory passage before
generation is even eligible. Fixtures assert the exact 79/80-character boundary,
60% density boundary and 2% invalid-character boundary, along with mixed pages.
This is an initial versioned eligibility rule, not a measured universal quality
classifier: repeated characters/digits can still pass, and short valid passages
or sparse mathematical pages can fail. It cannot establish factual completeness,
detect every bad OCR layer or validate semantic meaning. Later validation/review
must not equate this flag with trustworthy study content.

## Real resource bounds

Untrusted parsing occurs only in a disposable **Linux CPython process**. Before
importing pypdf or reading input, the child sets hard `RLIMIT_AS`, soft/hard
`RLIMIT_CPU`, and disables core dumps. The parent imposes a wall deadline and
kills/reaps a timed-out child. There is no shell invocation, inherited environment,
source-bearing diagnostic forwarding or parser output file. Bytecode writes
are disabled. These are resource limits, not a filesystem/network security sandbox.
After installing OS limits, the isolated child also recognizes the fixed
deployment-owned `backend/.python_packages/lib/site-packages` directory used by
Functions packaging. It does not inherit environment-controlled Python paths
or credentials. A real-parser fixture verifies this layout in a clean
interpreter with no globally installed parser.

| Default | Unit / enforcement |
| --- | --- |
| Input 16 MiB | Original bytes, checked before process launch and child read |
| Pages 100 | Physical page count before extraction; page-tree parsing itself is OS-bounded |
| Content stream 8 MiB | Decoded bytes per examined page/Form content stream |
| Total content 32 MiB | Sum of those examined decoded bytes; repeated Form invocations count again |
| Output 1,000,000 | Normalized Unicode code points summed across pages; no truncation |
| Form depth 32 | Maximum nested invoked Form objects; cycles are corrupt |
| Memory 512 MiB | Hard child **virtual address space**, not RSS or total Function-instance memory |
| CPU 10 seconds | Child CPU time, soft signal at 10, hard kill at 11 |
| Wall 15 seconds | Parent deadline including child startup and pipe transfer |

`PdfLimits` accepts positive integer trusted configuration overrides; form depth
and sufficiency thresholds are fixed/versioned. Limits are per invocation, not
global admission control. Input bytes already present in the caller, parent
result decoding, other workers and runtime overhead are outside the child's
memory cap. Future queue concurrency must budget these within the selected
2,048 MB Functions instance and enforce atomic quotas separately.

Decoded-size checks run **after** decompression; text-size checks run after page
extraction. Neither pretends to bound prior allocation or CPU work. The OS
address-space/CPU limits and wall timeout provide those actual bounds, including
font maps, object streams, malicious page trees and compressed expansion.
pypdf's additional built-in limits remain enabled; `LimitReachedError` yields
`resource_limit / native_parser_limit`. Examined content-byte totals are not a
claim to count every internal parser allocation or every font/image stream.

The child disables pypdf's optional JBIG2 executable through its supported
configuration API, including legacy configuration overrides. This prevents
decoder subprocesses/temporary files from escaping the native-text resource
boundary. A stream requiring an unavailable feature is explicitly unsupported.

pypdf otherwise attempts empty-password verification during reader construction.
A small pinned `PdfReader._handle_encryption` override instead aborts immediately
with an encrypted outcome before decryption/page access. This deliberately
depends on a private initialization hook in **7.1.1**; parser upgrades must rerun
RC4/AES and missing-provider tests before changing the pin. Encrypted payloads
are identified, not decrypted or validated internally.

`SIGKILL`/fixed memory-failure exits are reported as
`process_memory_or_termination`: the parent cannot prove whether an external
kill, hard CPU kill or failed memory allocation caused every abrupt termination.
Other unexpected exits are parser failures, never corrupt-input success.
Non-Linux platforms fail closed because equivalent hard address-space
enforcement is not established; there is no unsafe native fallback on macOS.

## Focused verification

All fixtures are original synthetic bytes generated by
`backend/extraction/tests/fixtures.py`. AES encryption uses randomized ciphertext
but its extraction outcome is deterministic; digital PDF bytes/results are
asserted repeatable. No private, downloaded or copyrighted study materials are
used. The large expansion and repeated-Form fixtures are intentionally hostile
synthetic documents, not production performance benchmarks.

```sh
cd backend
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -B -m pytest
```

This runs the complete backend suite, including extraction. Use
`.venv/bin/python -B -m pytest extraction/tests` for just this slice.
The existing authentication dependency supplies crypto for the AES fixtures;
the scoped extraction development manifest additionally pins it for standalone
fixture environments.

On Linux extraction tests invoke the public process-isolated extractor with the real
parser, including actual CPU exhaustion, wall timeout, compressed-memory
exhaustion, built-in decompression limits, and post-failure recovery.
On macOS only trusted synthetic fixtures call the internal parser; Linux-only
resource tests are skipped and the public fail-closed behavior is checked.
Do not use the internal parser with real/untrusted input on any platform.

Linux verification was also run in a disposable local Python 3.13 container,
with networking disabled, a read-only checkout/root filesystem, 1 GiB container
memory, two CPUs, a PID limit and no Linux capabilities. Disable bytecode/cache
writes to avoid shared cross-platform test artifacts.

Real Azure Functions host subprocess behavior, deployed Linux OS-limit
availability, concurrent workload headroom and representative real-document
fidelity/performance remain release gates. No real Functions/Azure/Anki smoke,
deployment or paid service was performed for this slice.
