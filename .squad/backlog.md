# Squad Implementation Backlog

Canonical Squad offline backlog (`templates/prd-intake.md`); requirements remain
the live [GitHub issues](https://github.com/lucusc/anki-ai-deck-generator/issues).
Snapshot: 2026-11-21 UTC, all 48 issues open; all acceptance criteria and appended
OAuth/temporary-retention requirements reviewed. #6 implementation is integrated
and offline-verified; real Functions host/cloud smoke remains pending. #1 is
integrated and offline-verified; actual Anki/OS-store/provider smoke remains
pending. Neither foundation is production-certified or closed on GitHub.

## Dependency-ready V1 waves

These are topological levels computed only from each issue's **Direct
prerequisites**, not issue numbering or roadmap milestone order. A ready issue
may proceed as soon as its own prerequisites are integrated and verified; it
need not wait for unrelated members of an earlier wave. Same-wave issues can
still share files/contracts, so lead must partition scopes before dispatch.

| Wave | Issues |
|------|--------|
| 0 | #1, #6 |
| 1 | #3, #4, #9, #10, #11, #12, #18, #21, #31, #32, #34 |
| 2 | #7, #13, #14, #19, #25, #33, #35, #37 |
| 3 | #2, #15, #20, #26, #27, #28, #29, #30, #36, #38 |
| 4 | #16, #39 |
| 5 | #17, #40 |
| 6 | #8, #22, #41 |
| 7 | #5, #23 |
| 8 | #24, #42 |

Initial independent work: **#1 (addon)** and **#6 (functions)**, after lead
aligns the shared API/payload/auth configuration contracts. #1 includes browser
OAuth PKCE and protected credential storage, not just a menu scaffold.

## V1 queue and ownership

Route = suggested accountable specialist, **not a claim**. Active claim is
`unclaimed` until the parent records session ID/branch/scope/prerequisite evidence
in `.squad/orchestration-log/` and this table. `ready` here means no graph
prerequisite, not implementation or permission. All other V1 work is `blocked`
on the listed prerequisites; completion requires the full issue acceptance.

| Issue | Title | Direct prerequisites | Route | Wave | State | Active claim |
|-------|-------|----------------------|-------|------|-------|--------------|
| #1 | Create Anki add-on project structure | None | addon | 0 | accepted offline; desktop/provider smoke pending | released; `0c0ce0a`, `a13c5c4` |
| #2 | Build file upload interface | #1, #7 | addon | 3 | blocked | unclaimed |
| #3 | Implement deck selector | #1 | addon | 1 | assigned | Deck selector; identity appended before execution |
| #4 | Implement audience selector | #1 | addon | 1 | ready | unclaimed; serialize shared UI wiring after #3 |
| #5 | Create review summary screen | #2, #8, #25 | addon | 7 | blocked | unclaimed |
| #6 | Create Azure Function project | None | functions | 0 | accepted offline; host/cloud smoke pending | released; `032393e`, `9f7311f` |
| #7 | Implement document upload endpoint | #6, #18, #21 | functions | 2 | blocked | unclaimed |
| #8 | Implement card generation endpoint | #7, #9, #16, #17 | functions | 6 | blocked | unclaimed |
| #9 | Support PDF extraction using PyMuPDF | #6 | pipeline | 1 | assigned | `98b8c5f4-5b32-4a3a-84dc-4ba470a7be4f`; initial `lucusc-super-adventure` |
| #10 | Support DOCX extraction | #6 | pipeline | 1 | ready | unclaimed |
| #11 | Support PowerPoint extraction | #6 | pipeline | 1 | ready | unclaimed |
| #12 | Support Markdown extraction | #6 | pipeline | 1 | ready | unclaimed |
| #13 | Implement OCR fallback path | #9, #18, #32 | pipeline | 2 | blocked | unclaimed |
| #14 | Create subject detection workflow | #9, #12 | pipeline | 2 | blocked | unclaimed |
| #15 | Implement card-type classification | #14 | pipeline | 3 | blocked | unclaimed |
| #16 | Develop Anki generation prompt | #15 | pipeline | 4 | blocked | unclaimed |
| #17 | Implement card quality validation | #16 | pipeline | 5 | blocked | unclaimed |
| #18 | Implement Blob Storage integration | #6 | functions | 1 | ready | unclaimed; defer dispatch until #21 storage contract is reconciled |
| #19 | Implement file hash tracking | #18, #21 | functions | 2 | blocked | unclaimed |
| #20 | Prevent duplicate file processing | #19 | functions | 3 | blocked | unclaimed |
| #21 | Implement Azure Table Storage schema | #6 | functions | 1 | assigned | `28606417-5782-4a37-a98b-72a5a835744a`; initial `lucusc-psychic-winner` |
| #22 | Create concept hash generation | #17 | pipeline | 6 | blocked | unclaimed |
| #23 | Implement duplicate card check | #21, #22 | functions | 7 | blocked | unclaimed |
| #24 | Skip duplicate card insertion | #23, #25 | addon | 8 | blocked | unclaimed |
| #25 | Create note model mapper | #1, #3 | addon | 2 | blocked | unclaimed |
| #26 | Support Basic notes | #25 | addon | 3 | blocked | unclaimed |
| #27 | Support Reverse notes | #25 | addon | 3 | blocked | unclaimed |
| #28 | Support Cloze notes | #25 | addon | 3 | blocked | unclaimed |
| #29 | Support custom tags | #25 | addon | 3 | blocked | unclaimed |
| #30 | Store source metadata in notes | #25 | addon | 3 | blocked | unclaimed |
| #31 | Add Application Insights integration | #6 | functions | 1 | ready | unclaimed |
| #32 | Track generation cost estimates | #6 | functions | 1 | ready | unclaimed |
| #33 | Track generation duration | #31 | functions | 2 | blocked | unclaimed |
| #34 | Create Bicep deployment templates | #6 | functions | 1 | ready | unclaimed |
| #35 | Create GitHub Actions deployment pipeline | #34 | functions | 2 | blocked | unclaimed |
| #36 | Automate dev environment deployment | #34, #35 | functions | 3 | blocked | unclaimed |
| #37 | Extract images from uploaded content | #9, #10, #11, #18 | pipeline | 2 | blocked | unclaimed |
| #38 | Detect diagrams suitable for image occlusion | #37 | pipeline | 3 | blocked | unclaimed |
| #39 | Generate occlusion masks from labels | #38, #13 | pipeline | 4 | blocked | unclaimed |
| #40 | Create Image Occlusion note generator | #25, #39 | addon | 5 | blocked | unclaimed |
| #41 | Support Anki Image Occlusion Enhanced compatibility | #40 | addon | 6 | blocked | unclaimed |
| #42 | Add image occlusion review screen | #5, #39, #40, #41 | addon | 8 | blocked | unclaimed |

tester is the independent verification route across all waves; lead owns
cross-domain contracts and acceptance/blocker reconciliation. #35/#36 queue
membership does not authorize deployment or spending.

## Post-V1: explicitly held

Do not dispatch #43-48 during V1 even if their graph prerequisites complete.
They are not V1 release gates. Their exact prerequisite edges remain visible:

| Issue | Title | Direct prerequisites | Route | State | Active claim |
|-------|-------|----------------------|-------|-------|--------------|
| #43 | Generate APKG packages | #24, #26, #27, #28, #40 | addon | post-V1 hold | unclaimed |
| #44 | Generate exam-focused decks | #17, #24 | pipeline | post-V1 hold | unclaimed |
| #45 | Generate learning-focused decks | #17, #24 | pipeline | post-V1 hold | unclaimed |
| #46 | Regenerate cards from source file | #20, #24, #30 | pipeline | post-V1 hold | unclaimed |
| #47 | Chapter-to-midterm review deck generation | #30, #44, #45 | pipeline | post-V1 hold | unclaimed |
| #48 | Deck sharing and export | #43 | addon | post-V1 hold | unclaimed |

After the V1 acceptance gate and separate scope authorization, #43-46 have no
remaining post-V1 predecessors; #47 depends on #44/#45 and #48 on #43.

## Refresh procedure

The parent reads all live issue bodies/state before selecting work, re-extracts
only the Direct prerequisites section, checks references/cycles, and reconciles
the tables/waves. Preserve explicit release scope and current ownership.
Changed criteria must flow into accepted decisions and assigned child context.
Do not invent missing prerequisites or treat a closed issue as sufficient
without integrated implementation evidence.
