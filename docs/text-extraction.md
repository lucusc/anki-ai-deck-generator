# Native TXT and Markdown extraction (#12)

`backend/extraction/` exposes deterministic native extraction for UTF-8 TXT and
Markdown. This is a local parser contract, not upload, Blob, Queue, OCR,
chunking, generation or Anki integration. It uses only Python's standard
library; no source markup is rendered or executed.

## Public contract

Run from the Functions module root and import the package as `extraction`:

```python
from extraction import TextOutcome, extract_markdown, extract_txt

result = extract_markdown(document_bytes)
if result.outcome == TextOutcome.OK:
    for section in result.sections:
        use_source_section(section.headings, section.line_start, section.line_end, section.text)
else:
    handle_document_outcome(result.outcome, result.reason)
```

`extract_txt(data: bytes, limits: TextLimits = TextLimits())` and
`extract_markdown(data: bytes, limits: TextLimits = TextLimits())` accept
immutable original bytes. Other input types raise `TypeError`. Input is decoded
as strict UTF-8; an optional UTF-8 BOM is accepted. CRLF and CR are normalized
to LF, and decoded text is normalized to Unicode NFC. Source lines are one-based
after newline normalization; content and section ordering follow source order.

Results and sections are frozen dataclasses. `TextExtraction` carries the
outcome, input format, ordered section tuple, fixed reason code and version
`text-native-1`. Each `TextSection` has a heading path, one-based inclusive
`line_start` / `line_end`, and its literal text. Plain text yields one
unheaded section. Markdown recognizes ATX headings (`#` through `######`) and
Setext headings (`===` / `---`), maintains nested heading paths, and retains
unheaded preamble as a section. A heading-only Markdown document preserves its
heading with an empty body. Fenced code is retained literally and headings
inside it are not interpreted. Other Markdown syntax is not parsed or rewritten.

| Outcome | Reason | Meaning |
| --- | --- | --- |
| `ok` | `None` | Complete ordered sections, including an empty-body heading when present |
| `empty` | `empty_document` | Empty or whitespace-only UTF-8 input |
| `invalid_encoding` | `invalid_utf8` | Input is not valid UTF-8; no partial text is returned |
| `resource_limit` | `input_bytes`, `line_count`, `section_count`, or `output_characters` | Input exceeds a configured bound; no partial sections are returned |

Default `TextLimits` are 4 MiB input bytes, 100,000 normalized lines, 10,000
sections, and 1,000,000 output characters. Bounds are inclusive and validated
as positive, non-boolean integers. Output characters count section text plus
heading labels (including repeated ancestor labels in nested heading paths).
Input/output are never silently truncated. These simple, linear passes use no
external parser, process, network, decompressor or filesystem access; they do
not add a wall-clock sandbox. Callers must still enforce upload and concurrency
quotas at their own boundaries.

Source bytes are untrusted data. HTML, links, code fences, scripts and other
embedded text remain inert strings; consumers must not evaluate, execute or
render them as trusted markup. This extraction layer performs no sanitization
or content interpretation. The line references and headings provide
provenance, not semantic validation or proof that content is suitable for
generation.

## Focused verification

Tests use synthetic UTF-8 data only:

```sh
cd backend
python3.13 -m pytest extraction/tests/test_text.py
```

Coverage includes BOM and Unicode normalization, exact byte/line/section/output
bounds, empty and invalid UTF-8 outcomes, one-based line references, nested
ATX/Setext headings, fenced code, heading-only Markdown, immutable results,
and literal unexecuted markup. These tests do not verify Azure, Functions-host,
Anki or generation integration.
