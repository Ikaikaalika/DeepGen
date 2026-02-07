# DeepGen

DeepGen is a cloud-first genealogy research bot scaffold focused on finding missing ancestors from a master GEDCOM and producing source-backed updates.

## What this scaffold includes
- GEDCOM ingest and export for `5.5.1` and `7.0`.
- Missing-ancestor gap detection from parsed family links.
- Living-person safety controls:
  - Living people are blocked by default.
  - Per-person consent for `allow data use` and `allow LLM research`.
  - `Mark All` bulk consent action.
- Provider configuration endpoints and UI fields for API keys.
- Research pipeline skeleton with source connectors and LLM backend abstraction.
- LLM backend options:
  - OpenAI (API key + model).
  - Local MLX (`mlx-lm`) for on-device inference on Apple Silicon.

## Recommended source APIs to start
- FamilySearch Developer Platform (primary genealogy API path).
- NARA Catalog API (US archival records).
- Library of Congress APIs (public historical collections).

## Quick start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn deepgen.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Use local MLX LLM
```bash
pip install -e .[mlx]
```

Then in the UI:
- Set `LLM Backend` to `mlx`.
- Set `MLX Model` (example: `mlx-community/Llama-3.2-3B-Instruct-4bit`).

## Configure keys
Use the UI form in section `Provider Config` to set:
- OpenAI API key/model
- FamilySearch client credentials
- NARA API key
- LLM backend (`openai`, `mlx`, or `none`)

Keys are stored in local SQLite for this scaffold environment.
