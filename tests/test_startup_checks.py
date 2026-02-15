import pytest

pytest.importorskip("pydantic_settings")

from deepgen.config import get_settings
from deepgen.services.startup_checks import run_startup_preflight


def test_startup_preflight_ok_in_writable_workspace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./tmp/deepgen.db")
    monkeypatch.setenv("LLM_BACKEND", "openai")
    get_settings.cache_clear()

    result = run_startup_preflight()

    assert result.ok is True
    assert result.errors == []

    get_settings.cache_clear()
