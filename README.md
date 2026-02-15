# DeepGen

DeepGen is a local-first genealogy research app scaffold focused on finding missing ancestors from a master GEDCOM and producing source-backed updates.

## What this scaffold includes
- GEDCOM ingest and export for `5.5.1` and `7.0`.
- Missing-ancestor gap detection from parsed family links.
- Living-person safety controls:
  - Living people are blocked by default.
  - Per-person consent for `allow data use` and `allow LLM research`.
  - `Mark All` bulk consent action.
- Provider configuration endpoints and UI fields for API keys.
- Deep research pipeline with evidence aggregation from internet and local folders.
- Local folder indexing so users can connect their own archive directory on macOS.
- Facial recognition pairing endpoint (optional install) for matching unlabeled photos to known people.
- LLM backend options:
  - OpenAI (API key + model).
  - Anthropic Claude (API key + model).
  - Local MLX (`mlx-lm`) for on-device inference on Apple Silicon.

## Current source connectors
- FamilySearch web search + optional direct API search (`access_token`).
- NARA Catalog API (live fetch + parsed candidates).
- Library of Congress API (live fetch + parsed candidates).
- Census surname API connector.
- GNIS dataset connector (local downloaded dataset path).
- GeoNames API connector.
- Wikidata entity search connector.
- Europeana API connector.
- OpenRefine reconciliation connector.
- Social lead connector (X, LinkedIn, Reddit, GitHub, optional Facebook/Instagram/Bluesky).
- Local folder connector (filename/content hints + citations).

## Quick start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn deepgen.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Run as a mac desktop app
```bash
pip install -e .[macapp]
deepgen-mac
```

This launches FastAPI locally and opens a native desktop window via `pywebview`.

## Sprint 1 release pipeline (macOS)
- Build app + dmg: `bash scripts/release/build_macos_app.sh`
- Notarize dmg: `bash scripts/release/notarize_macos.sh dist/DeepGen.dmg`
- Smoke-test artifact: `bash scripts/release/smoke_test_macos_artifact.sh`
- Generate update feed: `python3 scripts/release/generate_update_feed.py --version 0.1.0-beta.1 --download-url <url>`
- GitHub preflight + dispatch: `bash scripts/release/github_release_preflight.sh 0.1.0-beta.1 test`

CI workflow:
- `/.github/workflows/macos-release.yml`
- Supports manual dispatch and tag-based release (`v*` tags).
- Uses optional secrets for signing/notarization:
  - `MACOS_CODESIGN_IDENTITY`
  - `APPLE_ID`
  - `APPLE_TEAM_ID`
  - `APPLE_APP_PASSWORD`

Update checks:
- Set `DEEPGEN_UPDATE_FEED_URL` (for example to `releases/test/appcast.json` hosted URL).
- Use UI buttons `Refresh App Status` and `Check Updates`.

## Deep research workflow
1. Configure provider keys and set a local folder path in `Provider Config`.
2. Upload GEDCOM and review living-person consent.
3. Upload user documents in section `User File Uploads + Index` (optional but recommended).
4. Run `Load Missing Ancestor Gaps`.
5. Run `Index Local Folder` to validate your archive connection.
6. Run `Run Research Job` to execute the staged v2 pipeline:
   - retrieval -> extraction -> contradiction checks -> proposal synthesis.
   - includes evidence from indexed user-uploaded files automatically.
7. Answer agent-generated research questions in `question-review` to resolve evidence gaps.
8. Review proposals in `pending_review` and approve/reject/edit manually.
9. Run `Apply Approved Proposals` to update parent links with audit events.
10. Optionally run `Run Face Pairing` for unlabeled image matching.

## Research v2 API
- `POST /api/sessions/{session_id}/research/jobs`
- `GET /api/research/jobs/{job_id}`
- `GET /api/research/jobs/{job_id}/findings`
- `GET /api/research/jobs/{job_id}/proposals`
- `GET /api/research/jobs/{job_id}/questions`
- `POST /api/research/proposals/{proposal_id}/decision`
- `POST /api/research/questions/{question_id}/answer`
- `POST /api/sessions/{session_id}/research/apply-approved`

## User Document Index API
- `POST /api/sessions/{session_id}/documents/upload` (multipart `file`)
- `GET /api/sessions/{session_id}/documents`
- `GET /api/sessions/{session_id}/documents/search?q=<query>`
- `POST /api/sessions/{session_id}/documents/reindex`

## Migrations (Alembic)
```bash
alembic upgrade head
```

## Use local MLX LLM
```bash
pip install -e .[mlx]
```

Then in the UI:
- Set `LLM Backend` to `mlx`.
- Set `MLX Model` (example: `mlx-community/Llama-3.2-3B-Instruct-4bit`).

## Use Anthropic Claude
Then in the UI:
- Set `LLM Backend` to `anthropic`.
- Set `Anthropic API Key`.
- Set `Anthropic Model` (example: `claude-3-5-sonnet-latest`).

## Enable facial recognition pairing
```bash
pip install -e .[vision]
```

Then:
- Provide a local folder path with photos.
- Name a subset of images with person names to establish references (for example: `john_doe_1940.jpg`).
- Run `Run Face Pairing`.

## Configure keys
Use the UI form in section `Provider Config` to set:
- OpenAI API key/model
- Anthropic API key/model
- FamilySearch client credentials + access token
- NARA API key
- LOC API key
- Census API key + enabled toggle
- GNIS dataset path + enabled toggle
- GeoNames username + enabled toggle
- Wikidata enabled toggle
- Europeana API key + enabled toggle
- OpenRefine reconciliation URL + enabled toggle
- Social lead connector + platform toggles (X, LinkedIn, Reddit, GitHub, Facebook, Instagram, Bluesky)
- Local folder path + enabled toggle
- Face threshold
- LLM backend (`openai`, `anthropic`, `mlx`, or `none`)

Secret fields (API keys/secrets/tokens/passwords) are stored in macOS Keychain when available.
Non-secret provider settings are stored in local SQLite.

Keychain backend controls:
- `DEEPGEN_KEYCHAIN_BACKEND=auto` (default): use macOS Keychain on macOS, otherwise fallback to local config.
- `DEEPGEN_KEYCHAIN_BACKEND=security`: force macOS Keychain backend.
- `DEEPGEN_KEYCHAIN_BACKEND=disabled`: disable Keychain backend.

Key update behavior:
- Leaving a secret field blank in the UI preserves the existing stored secret.
- To clear a secret via API, send `__DELETE__` for that field.
