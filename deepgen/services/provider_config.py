import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from deepgen.config import get_settings
from deepgen.models import ProviderConfig

SECRET_FIELD_MARKERS = ("key", "secret", "token", "password")
SUPPORTED_PROVIDERS = ("openai", "familysearch", "nara", "loc", "llm", "mlx", "ocr")


def _default_configs() -> dict[str, dict[str, str]]:
    settings = get_settings()
    return {
        "openai": {
            "api_key": settings.openai_api_key or "",
            "model": settings.openai_model,
        },
        "llm": {
            "backend": settings.llm_backend,
        },
        "mlx": {
            "enabled": "true" if settings.enable_mlx else "false",
            "model": settings.mlx_model,
        },
        "familysearch": {
            "client_id": "",
            "client_secret": "",
        },
        "nara": {
            "api_key": "",
        },
        "loc": {
            "api_key": "",
        },
        "ocr": {
            "provider": "tesseract",
        },
    }


def _is_secret(field: str) -> bool:
    lowered = field.lower()
    return any(marker in lowered for marker in SECRET_FIELD_MARKERS)


def _mask_value(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def get_provider_config(db: Session, provider: str) -> dict[str, str]:
    provider = provider.lower()
    defaults = _default_configs().get(provider, {})
    row = db.get(ProviderConfig, provider)
    if not row:
        return defaults
    try:
        data = json.loads(row.config_json)
    except json.JSONDecodeError:
        data = {}
    merged = {**defaults, **{k: str(v) for k, v in data.items()}}
    return merged


def list_provider_configs(db: Session) -> dict[str, dict[str, str]]:
    return {provider: get_provider_config(db, provider) for provider in SUPPORTED_PROVIDERS}


def list_provider_configs_masked(db: Session) -> dict[str, dict[str, str]]:
    masked: dict[str, dict[str, str]] = {}
    for provider, values in list_provider_configs(db).items():
        masked[provider] = {}
        for key, value in values.items():
            if not value:
                masked[provider][key] = ""
                continue
            masked[provider][key] = _mask_value(value) if _is_secret(key) else value
    return masked


def update_provider_config(db: Session, provider: str, values: dict[str, str]) -> dict[str, str]:
    provider = provider.lower()
    row = db.get(ProviderConfig, provider)
    current = get_provider_config(db, provider)
    for key, value in values.items():
        current[key] = value
    if row is None:
        row = ProviderConfig(
            provider=provider,
            config_json=json.dumps(current),
            updated_at=datetime.now(UTC),
        )
        db.add(row)
    else:
        row.config_json = json.dumps(current)
        row.updated_at = datetime.now(UTC)
    db.commit()
    return get_provider_config(db, provider)
