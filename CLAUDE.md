# CLAUDE.md

Guidance for AI assistants (Claude Code and similar) working in this repository.

## What this project is

DeepGen is a local-first genealogy research application built as a FastAPI
backend that ships either as a web app (`uvicorn`) or as a notarized macOS
desktop app (FastAPI + `pywebview` packaged with PyInstaller). It ingests a
GEDCOM, identifies missing-ancestor gaps, runs a multi-stage research pipeline
(retrieval → extraction → contradiction checks → proposal synthesis) backed by
OpenAI / Anthropic / local MLX, and surfaces source-cited proposals for human
review before any GEDCOM update is applied.

Privacy and consent are first-class: living people are blocked by default, the
research pipeline only runs on consenting subjects, and proposals never auto-apply.

## Repository layout

```
deepgen/
  main.py                        FastAPI app, /api/health, /api/app/*, /api/ocr
  mac_app.py                     pywebview launcher; spawns uvicorn on 127.0.0.1:8765
  config.py                      pydantic-settings (.env loader); cached via lru_cache
  db.py                          SQLAlchemy 2.x DeclarativeBase, engine, get_db()
  models.py                      All ORM models (single file)
  schemas.py                     All Pydantic request/response models (single file)
  version.py                     get_app_version() via importlib.metadata
  routers/
    config_router.py             /api/providers/config*  (provider config CRUD)
    sessions_router.py           /api/sessions/*         (GEDCOM upload, consent, docs)
    research_router.py           /api/sessions/{id}/research/*, /api/research/*
  services/
    gedcom.py                    GEDCOM 5.5.1 / 7.0 parser + exporter
    research.py                  gap_candidates() (consent-safe missing-parent finder)
    connectors.py                Source connectors (FamilySearch, NARA, LOC, Census,
                                 GNIS, GeoNames, Wikidata, Europeana, OpenRefine,
                                 social leads, local folder)
    source_types.py              SourceResult dataclass shared by connectors
    llm.py                       LLMClient base + OpenAIClient/AnthropicClient/MLXClient
    provider_config.py           Provider config persistence + masking
    keychain.py                  macOS `security` shell-out + memory/disabled fallbacks
    document_index.py            User document upload + content indexing
    local_files.py               Local archive folder indexer
    faces.py                     Optional face_recognition pairing
    ocr.py                       Optional pytesseract OCR
    startup_checks.py            run_startup_preflight() (writable paths, keychain)
    updater.py                   Appcast-based update check
    research_pipeline/
      jobs.py                    create_research_job / run_research_job orchestration
      retrieval.py               Connector fan-out + deduplication
      extraction.py              LLM claim extraction with JSON repair pass
      contradictions.py          Heuristic contradiction flags
      scoring.py                 Proposal synthesis + final_score formula
      backend_adapters.py        resolve_runtime() -> LLMRuntime for jobs
      apply.py                   apply_approved_proposals() with audit trail
  templates/index.html, static/{app.js,styles.css}   Single-page UI
alembic/                         Migrations (env reads deepgen.config.Settings)
  versions/20260215_000{1,2,3}_*.py
tests/                           pytest suite (uses sqlite:///:memory: + monkeypatch)
scripts/release/                 macOS build / notarize / smoke / appcast scripts
.github/workflows/macos-release.yml   CI for tag + manual-dispatch builds
docs/                            SPRINT_MANAGEMENT.md and release runbooks
```

## Tech stack

- Python `>=3.11` (CI uses 3.12; release script picks the newest available 3.11–3.13).
- FastAPI + Uvicorn, Jinja2 templates for the UI shell, plain JS in `static/`.
- SQLAlchemy 2.x ORM with `DeclarativeBase`, default DB is SQLite (`./deepgen.db`).
- Alembic for schema migrations (current head: `20260215_0003_research_questions`).
- Pydantic v2 + `pydantic-settings` for config.
- Optional extras: `mlx-lm` (`[mlx]`), `face-recognition`+`pillow` (`[vision]`),
  `pytesseract`+`pillow` (`[ocr]`), `pywebview` (`[macapp]`), `pytest`+`ruff` (`[dev]`).

## Common workflows

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# Run web UI
uvicorn deepgen.main:app --reload     # http://127.0.0.1:8000

# Run desktop app (after pip install -e .[macapp])
deepgen-mac                            # spawns uvicorn on 127.0.0.1:8765 + webview

# DB migrations
alembic upgrade head
alembic revision -m "describe change"  # autogenerate is NOT wired; write ops by hand

# Tests + lint
pytest                                 # config in pyproject.toml [tool.pytest.ini_options]
ruff check .

# macOS release pipeline
bash scripts/release/build_macos_app.sh
bash scripts/release/notarize_macos.sh dist/DeepGen.dmg
bash scripts/release/smoke_test_macos_artifact.sh dist/DeepGen.app dist/DeepGen.dmg
python3 scripts/release/generate_update_feed.py --version X.Y.Z --download-url <url>
```

## Architectural conventions

### Single-file boundaries
- All ORM models live in `deepgen/models.py`. All Pydantic schemas live in
  `deepgen/schemas.py`. Don't split these into per-feature modules without a
  reason — existing imports assume the flat layout.
- Routers stay thin: parse the request, look up the session, delegate to a
  service, map the result to a schema. Business logic belongs in
  `deepgen/services/`, not in routers.

### Research pipeline
The pipeline is staged and synchronous within a request — `create_research_job`
inserts a `ResearchJob` row, then `run_research_job` (called inline in
`research_router.create_session_research_job`) iterates each candidate person
through retrieval → extraction → verification → synthesis, persisting
`EvidenceItem` / `ExtractedClaim` / `ParentProposal` / `ResearchQuestion` rows
as it goes. Stage timings and errors accumulate in `ResearchJob.stage_stats_json`.

When extending the pipeline, preserve these invariants:
- A proposal cannot be approved without `candidate_name` and at least one
  `evidence_id` (enforced in `decide_proposal`).
- `apply_approved_proposals` is idempotent against already-linked parents and
  always writes an `ApplyAuditEvent`, even on skip.
- `_select_candidates` filters out living people without both `can_use_data`
  and `can_llm_research`. Don't bypass that gate.
- Connector failures are isolated per connector (see `_filtered_connectors`
  and the `_BadConnector` test); a single bad source must not fail the job.
- LLM extraction has one repair pass (`_build_repair_prompt`) when JSON parse
  fails. Keep `parse_repair_count` accurate when adding new repair paths.

### Provider config + secrets
- `provider_config.py` persists non-secret fields in the `provider_configs`
  SQLite table and routes any field whose name contains
  `key|secret|token|password` into the keychain backend.
- Keychain backend is selected by `DEEPGEN_KEYCHAIN_BACKEND`
  (`auto`/`security`/`memory`/`disabled`); auto picks `security` on macOS,
  otherwise falls back to plaintext in SQLite.
- `__DELETE__` is the API sentinel for clearing a secret. A blank value
  preserves the existing secret. Masked values matching `^\*{4,}[A-Za-z0-9]{0,4}$`
  are treated as no-op echoes from the UI.
- On read, legacy plaintext secrets are migrated into the keychain on the
  fly. Don't add code paths that re-write secrets back into SQLite.

### Living-person consent
- `Person.is_living` defaults to `True` (conservative). `infer_living_status`
  in `services/gedcom.py` only marks someone non-living if a death date exists
  or `birth_year <= current_year - 120`.
- `can_use_data` and `can_llm_research` default to `False` for living people.
  Any feature that operates on a person should respect both flags, mirroring
  `gap_candidates` and `_select_candidates`.

### Settings & DB
- `get_settings()` is `lru_cache`d — tests that mutate environment variables
  must clear the cache or use `monkeypatch.setenv` before first import.
- SQLite uses `check_same_thread=False`; FastAPI dependency `get_db` yields a
  scoped session per request. Don't create global sessions.

## Tests

- Suite: `pytest -q` (default from `pyproject.toml`). Tests run from repo root
  with `pythonpath = ["."]`.
- Pattern: in-memory SQLite (`create_engine("sqlite:///:memory:")`) +
  `Base.metadata.create_all(engine)` per test. See
  `tests/test_research_pipeline_jobs.py` for the canonical fixture.
- Pipeline tests `monkeypatch` `list_provider_configs`, `build_connectors`,
  and `resolve_runtime` to inject fake connectors and a stub LLM
  (`_StubLLM.generate` returns a hard-coded JSON envelope). Follow that
  pattern when adding pipeline tests — don't hit real providers.
- `pytest.importorskip("pydantic_settings")` is used at the top of tests that
  import settings; preserve this when adding tests that touch `deepgen.config`.

## CI / release

- `.github/workflows/macos-release.yml` runs on `macos-14`, on tag pushes
  matching `v*` and on manual `workflow_dispatch`.
- Optional secrets: `MACOS_CODESIGN_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`,
  `APPLE_APP_PASSWORD`. Build/notarize steps no-op gracefully when absent.
- Update-feed generation writes `releases/<channel>/appcast.json`. The
  desktop app polls `DEEPGEN_UPDATE_FEED_URL` non-blockingly on launch.

## Coding conventions

- `from __future__ import annotations` is used in most modules — keep it for
  PEP 604 type unions on 3.11.
- Type hints use `X | None` everywhere; match that style.
- Datetimes are timezone-aware UTC (`datetime.now(UTC)`); never use
  `datetime.utcnow()`.
- JSON-stored columns (e.g., `evidence_ids_json`, `score_components_json`,
  `stage_stats_json`) are `Text`; always go through the `_json_load_list` /
  `_json_load_dict` helpers in `jobs.py` (or local equivalents) — they
  tolerate corrupt rows by returning `[]` / `{}`.
- Internal helpers are prefixed with `_`. Don't re-export them.
- Comments are sparse and explain WHY, not WHAT (see `infer_living_status`
  for the conservative-privacy comment style).
- Errors raised from services use domain-specific exceptions
  (`LLMError`, `LocalFolderError`, `FacePairingError`, `DocumentIndexError`)
  which routers translate to `HTTPException` 4xx.

## What NOT to do

- Don't bypass the living/consent filter in `_select_candidates` or
  `gap_candidates`.
- Don't auto-apply proposals — `apply_approved_proposals` only runs on
  rows whose `status == "approved"` (set by an explicit user decision).
- Don't store secrets in `provider_configs` table directly. Always go
  through `update_provider_config` so the keychain path is taken.
- Don't widen `SUPPORTED_PROVIDERS` without also updating `_default_configs`,
  the UI form in `templates/index.html` + `static/app.js`, and tests.
- Don't use `git commit --no-verify` or amend pushed commits.

## Branch + commit policy for assistants

- Develop on the branch named in the task (currently
  `claude/add-claude-documentation-CMDau`); create it locally if missing.
- Commit with descriptive messages; push with
  `git push -u origin <branch>`. Do NOT open a PR unless explicitly asked.
- Restricted GitHub repo scope: `ikaikaalika/deepgen`. Don't touch others.
