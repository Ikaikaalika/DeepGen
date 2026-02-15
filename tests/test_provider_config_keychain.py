import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytest.importorskip("pydantic_settings")

from deepgen.db import Base
from deepgen.config import get_settings
from deepgen.models import ProviderConfig
from deepgen.services import keychain
from deepgen.services.provider_config import get_provider_config, update_provider_config


@pytest.fixture
def db_session(monkeypatch) -> Session:
    monkeypatch.setenv("DEEPGEN_KEYCHAIN_BACKEND", "memory")
    get_settings.cache_clear()
    keychain.clear_memory_store_for_tests()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        keychain.clear_memory_store_for_tests()
        get_settings.cache_clear()


def test_update_uses_keychain_for_secrets(db_session: Session):
    values = update_provider_config(
        db_session,
        "openai",
        {"api_key": "sk-test-1234", "model": "gpt-4.1-mini"},
    )

    row = db_session.get(ProviderConfig, "openai")
    assert row is not None
    payload = json.loads(row.config_json)

    assert payload.get("model") == "gpt-4.1-mini"
    assert "api_key" not in payload
    assert values["api_key"] == "sk-test-1234"
    assert keychain.get_secret("openai", "api_key") == "sk-test-1234"


def test_legacy_plaintext_secret_is_migrated(db_session: Session):
    row = ProviderConfig(
        provider="anthropic",
        config_json=json.dumps({"api_key": "legacy-ant-key", "model": "claude-3-5-sonnet-latest"}),
    )
    db_session.add(row)
    db_session.commit()

    values = get_provider_config(db_session, "anthropic")
    db_session.refresh(row)
    payload = json.loads(row.config_json)

    assert values["api_key"] == "legacy-ant-key"
    assert keychain.get_secret("anthropic", "api_key") == "legacy-ant-key"
    assert "api_key" not in payload


def test_blank_secret_update_preserves_existing_secret(db_session: Session):
    update_provider_config(db_session, "nara", {"api_key": "nara-secret-1"})

    values = update_provider_config(db_session, "nara", {"api_key": ""})

    assert values["api_key"] == "nara-secret-1"
    assert keychain.get_secret("nara", "api_key") == "nara-secret-1"


def test_delete_sentinel_removes_secret(db_session: Session):
    update_provider_config(db_session, "openai", {"api_key": "sk-delete-me"})

    values = update_provider_config(db_session, "openai", {"api_key": "__DELETE__"})

    assert values["api_key"] == ""
    assert keychain.get_secret("openai", "api_key") is None


def test_delete_sentinel_overrides_env_default(monkeypatch, db_session: Session):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-default")
    get_settings.cache_clear()

    values = update_provider_config(db_session, "openai", {"api_key": "__DELETE__"})

    assert values["api_key"] == ""
