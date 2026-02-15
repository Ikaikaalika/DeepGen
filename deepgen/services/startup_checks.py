from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from deepgen.config import get_settings
from deepgen.services.provider_config import keychain_status


@dataclass
class StartupCheckResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


def _is_writable_path(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def run_startup_preflight() -> StartupCheckResult:
    settings = get_settings()
    errors: list[str] = []
    warnings: list[str] = []

    uploads_dir = Path("data/uploads")
    if not _is_writable_path(uploads_dir):
        errors.append(f"Uploads directory is not writable: {uploads_dir.resolve()}")

    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        sqlite_path = db_url.replace("sqlite:///", "", 1)
        db_file = Path(sqlite_path).expanduser()
        db_parent = db_file.parent
        if not _is_writable_path(db_parent):
            errors.append(f"Database directory is not writable: {db_parent.resolve()}")
    else:
        warnings.append("Non-sqlite database configured; startup write checks skipped.")

    if not settings.llm_backend:
        warnings.append("LLM backend is blank; research summaries will be disabled.")

    kc = keychain_status()
    if not kc["available"]:
        warnings.append("Keychain backend unavailable; sensitive provider keys may fall back to local config storage.")

    return StartupCheckResult(ok=not errors, errors=errors, warnings=warnings)
