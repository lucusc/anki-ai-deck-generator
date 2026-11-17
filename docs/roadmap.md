# Roadmap

## V1 milestones

1. **MVP:** add-on shell, asynchronous job plumbing, native extraction, generation/validation, and Anki note import.
2. **Deck Intelligence:** private storage, provenance, source/card duplicate prevention, authentication, observability, and reproducible infrastructure.
3. **Image Occlusion:** image extraction, candidate detection, mask generation, editable review, and tested Anki image occlusion compatibility.

All three milestones are required for V1. Image occlusion has deliberately been promoted from the original V2 outline. OCR fallback is included as an explicitly enabled, usage-bounded extraction path.

## Post-V1 milestones

4. **Study Modes:** dedicated exam/learning generation modes, regeneration, and cross-chapter review.
5. **Sharing:** APKG packaging and safe deck sharing/export.

## Backlog organization

The initial 48 issues preserve the supplied outline's ordering and titles. Labels identify epics, release scope, and priority. Milestones represent delivery stages, not separate products. Each issue records acceptance criteria and direct prerequisites.

Suggested implementation sequence:

- Establish add-on/API contracts and asynchronous jobs.
- Prove digital-PDF-to-reviewed-note import with test fixtures.
- Expand extraction formats and audience-aware generation.
- Complete storage, duplicate recovery, security, cost controls, and infrastructure before production use.
- Deliver image occlusion end to end before declaring V1 complete.
- Keep export, specialized modes, explicit regeneration controls, and cross-chapter review outside the V1 release gate.

A separate GitHub Projects board, if authorized, can track Backlog, Ready, In Progress, Review, Done, and Blocked. Repository issues and milestones remain usable without Projects permissions.
