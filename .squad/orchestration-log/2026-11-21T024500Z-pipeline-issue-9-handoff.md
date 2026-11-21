# Issue #9 handoff - pipeline

| Field | Evidence |
| --- | --- |
| Assignment | `2026-11-21T024500Z-pipeline-issue-9.md`; issue #9 only |
| Session | `98b8c5f4-5b32-4a3a-84dc-4ba470a7be4f` |
| Final branch | `lucusc-pdf-extraction` (app-managed rename before edits) |
| State / outcome | Committed offline implementation; ready for parent review, not release certification |
| Base | `5b771c24abe23992a2cce583d1bdad00391ee615` |
| Prerequisite | #6 integrated `032393e` / `9f7311f`, parent-reviewed 34 CPython 3.13 tests |
| Parent identity | `1c87f33928e011d391964826ff376ef7f2d25708` cherry-picked before file edits as `acdfdc3`; parent already owns the original identity changes |
| Implementation | `765d72ae59f35b522bb7dfbb4149f35401cb5450` |
| Handoff | This separate commit; send its SHA to parent after committing |
| Team state | Own worktree TEAM_ROOT / WORKTREE_PATH; STATE_BACKEND=local |

## Changed paths

- `backend/extraction/__init__.py`
- `backend/extraction/pdf.py`
- `backend/extraction/requirements.txt`
- `backend/extraction/requirements-dev.txt`
- `backend/extraction/THIRD_PARTY_NOTICES.txt`
- `backend/extraction/tests/fixtures.py`
- `backend/extraction/tests/test_pdf.py`
- `docs/pdf-extraction.md`
- `.squad/agents/pipeline/history.md`
- `.squad/decisions/inbox/pipeline-9-pdf-extraction.md`
- This uniquely named handoff record.

No backend/root manifests, Functions entrypoint/auth/worker, storage subtree,
README, shared decisions/backlog, other-member state, HTTP/Blob/Queue, OCR,
generation or other-format implementation was changed.

## Acceptance evidence

Ordered synthetic digital text is returned with every one-based physical page,
including blank separators. Repeated digital bytes and extraction results are
asserted deterministic. Plain mode preserves content-stream order, not arbitrary
visual/column order. Fixtures are original programmatically generated materials.

Reviewed PyMuPDF's AGPL/commercial terms and selected **pypdf 7.1.1,
BSD-3-Clause** without purchasing a license or adopting AGPL obligations. License
URLs/choice and retained redistribution notice are documented. The parent must
include the scoped runtime requirements when reconciling package manifests.
The test-only crypto provider creates genuine AES fixtures; it is not required
for runtime encryption recognition.

Explicit immutable outcomes cover encrypted RC4/AES (including empty passwords
and no crypto provider), corrupt/truncated/invalid PDF, image-only direct/Form/
inline images, unused image resources, empty/short/noisy and mixed scanned/
digital/vector pages, unsupported input/features and operational failures.
Parser warnings reject repaired/substituted results rather than returning success.
Hard failures discard partial text.

Eligibility is >=80 Unicode alphanumeric characters per nonblank page, >=60%
alphanumeric/non-whitespace density and <=2% replacement/control/format
characters. The precise boundaries are asserted with the actual parser and font
mapping. A strong page cannot hide an insufficient page. This is not a semantic
quality/completeness classifier.

**Actual Linux resource tests**, not input-size proxies: a <20,000-byte expanding
Form graph exhausts CPU and wall budgets; a <128 KiB compressed PDF exhausts an
80 MiB address-space limit before a decoded-size check could run. A subsequent
valid extraction succeeds. Native decompression-limit exceptions also produce
explicit resource outcomes. Input, pages, decoded-content, total decoded-content,
normalized output and nested-Form depth boundaries are exercised.

Defaults: 16 MiB original input; 100 pages; 8 MiB per examined decoded page/Form
content stream; 32 MiB cumulative examined decoded bytes, including repeated
invocations; 1,000,000 normalized output code points; 32 nested Forms; 512 MiB
hard child virtual address space; 10/11-second soft/hard CPU; 15-second parent
wall deadline. Limits are per process/invocation, not total instance or atomic
per-user admission limits. Size checks follow allocation; OS/wall limits guard
prior parser work.

Optional JBIG2 executable decoding is explicitly disabled, including legacy
overrides, to avoid descendant processes/image temp files. Core dumps,
inherited environment and bytecode writes are disabled; fixed operational codes
are logged, never text/exception diagnostics. No untrusted in-process fallback.

## Commands and results

macOS CPython **3.13.9**:

```sh
python3.13 -m venv backend/extraction/.venv
backend/extraction/.venv/bin/python -m pip install --quiet -r backend/extraction/requirements-dev.txt
backend/extraction/.venv/bin/python -B -m pytest -o addopts= -q backend/extraction/tests
```

**48 passed, 5 skipped**. Trusted synthetic fixtures use the internal parser on
macOS; the public fail-closed outcome is tested. Skips are Linux-only CPU, wall,
memory, native-limit and missing-crypto process cases.

Local Linux container, CPython **3.13.18**, real production process boundary:

```sh
docker build --quiet --tag anki-pdf-issue9-tests - <<'DOCKERFILE'
FROM python:3.13-slim
RUN pip install --no-cache-dir --quiet pypdf==7.1.1 pytest==8.4.2 cryptography==46.0.3
DOCKERFILE
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,nosuid,noexec,size=256m --memory 1g --cpus 2 --pids-limit 64 \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,source="$PWD",target=/workspace,readonly \
  --workdir /workspace anki-pdf-issue9-tests \
  python -B -m pytest -o addopts= -q -o cache_dir=/tmp/pytest-cache backend/extraction/tests
```

**52 passed, 1 skipped in 8.59s**. Only the non-Linux fail-closed test skips.
The container has no test-time networking, writable checkout or capabilities.
No service/watcher was left running.

Critical-gate mutation verification used disposable copies in the same Linux
container, never modifying the worktree. The session artifact
`files/verify_pdf_mutations.py` ran with `python -B /verify_pdf_mutations.py`
after a read-only bind of that script. **All 10 weakened implementations were
rejected by actual assertion failures**: minimum characters, density, invalid
characters, partial-page rejection, parser warnings, external-decoder disabling,
encryption hook, address-space ceiling, CPU ceiling and wall deadline.

`git diff --cached --check` passed before the implementation commit. Local
ignored virtual environments/caches are not in the commits.

## Proposed contracts and remaining gates

The unique decision inbox and `docs/pdf-extraction.md` contain exact fields/
units/outcomes. Parent/lead must accept this PDF-local contract before dependent
formats/jobs consume it; no sibling schema was assumed. Parent must reconcile
`backend/extraction/requirements.txt` and distribution notices.

The **private pinned `PdfReader._handle_encryption` initialization hook** aborts
at the parsed encrypted trailer before pypdf's automatic empty-password
verification; encrypted internal payloads are not decrypted/validated. Parser
upgrades must rerun genuine RC4/AES/provider-free tests. OS hard limits are
Linux-specific; macOS explicitly refuses untrusted extraction. These are resource
limits, not a filesystem/network sandbox. Abrupt SIGKILL/fixed memory exits have
the deliberately ambiguous `process_memory_or_termination` reason.

Real Functions-host subprocess/OS-limit availability, deployed Azure smoke,
concurrent memory headroom and representative real-PDF fidelity/performance were
**not** verified. No real Anki/Azure work, deployment, paid calls, nested agents/
sessions, GitHub writes or PRs were performed. #13 OCR and later temporary-storage,
expiry/deletion, quota, source-hash and generation responsibilities remain outside
this slice. Stop after handing these commits to the parent.
