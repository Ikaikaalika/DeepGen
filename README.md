# DeepGen

DeepGen is a cloud-first genealogy research agent designed to find missing ancestors from a master GEDCOM and propose source-backed updates.

## Scope
- Support both GEDCOM 5.5.1 and GEDCOM 7.0.
- Ingest a master GEDCOM, detect ancestor gaps, and generate research tasks.
- Search approved genealogy sources, collect records, download documents, OCR them, and extract evidence.
- Propose and apply GEDCOM updates with citation/provenance tracking.
- Exclude living people by default and require explicit per-person consent before LLM research.

## Living Person Safety Workflow
- Detect likely living people in uploaded GEDCOM files.
- Present a review list where users decide, per person:
  - Can this person’s data be used by the app?
  - Can the LLM research this person?
- If either is denied, block LLM processing for that person.
- Include a "Mark All" control to apply bulk consent decisions.

## Status
Initial project scaffold and repository setup.
