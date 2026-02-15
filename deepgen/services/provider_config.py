import json
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from deepgen.config import get_settings
from deepgen.models import ProviderConfig
from deepgen.services import keychain

SECRET_FIELD_MARKERS = ("key", "secret", "token", "password")
SUPPORTED_PROVIDERS = (
    "openai",
    "anthropic",
    "familysearch",
    "nara",
    "loc",
    "census",
    "gnis",
    "geonames",
    "wikidata",
    "europeana",
    "openrefine",
    "llm",
    "mlx",
    "ocr",
    "local",
    "face",
)
_CLEAR_SENTINEL = "__DELETE__"


def _default_configs() -> dict[str, dict[str, str]]:
    settings = get_settings()
    return {
        "openai": {
            "api_key": settings.openai_api_key or "",
            "model": settings.openai_model,
        },
        "anthropic": {
            "api_key": settings.anthropic_api_key or "",
            "model": settings.anthropic_model,
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
            "access_token": settings.familysearch_access_token or "",
        },
        "nara": {
            "api_key": settings.nara_api_key or "",
        },
        "loc": {
            "api_key": settings.loc_api_key or "",
        },
        "census": {
            "enabled": "false",
            "api_key": settings.census_api_key or "",
        },
        "gnis": {
            "enabled": "false",
            "dataset_path": settings.gnis_dataset_path or "",
        },
        "geonames": {
            "enabled": "false",
            "username": settings.geonames_username or "",
        },
        "wikidata": {
            "enabled": "true",
        },
        "europeana": {
            "enabled": "false",
            "api_key": settings.europeana_api_key or "",
        },
        "openrefine": {
            "enabled": "false",
            "service_url": settings.openrefine_service_url or "",
        },
        "ocr": {
            "provider": "tesseract",
        },
        "local": {
            "folder_path": "",
            "enabled": "false",
        },
        "face": {
            "enabled": "false",
            "threshold": "0.52",
        },
    }


def _is_secret(field: str) -> bool:
    lowered = field.lower()
    return any(marker in lowered for marker in SECRET_FIELD_MARKERS)


def _mask_value(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def _looks_masked(value: str) -> bool:
    return bool(re.fullmatch(r"\*{4,}[A-Za-z0-9]{0,4}", value))


def _load_row_data(row: ProviderConfig | None) -> dict[str, str]:
    if not row:
        return {}
    try:
        data = json.loads(row.config_json)
    except json.JSONDecodeError:
        data = {}
    return {k: str(v) for k, v in data.items()}


def _save_row_data(db: Session, provider: str, data: dict[str, str]) -> None:
    row = db.get(ProviderConfig, provider)
    if row is None:
        row = ProviderConfig(
            provider=provider,
            config_json=json.dumps(data),
            updated_at=datetime.now(UTC),
        )
        db.add(row)
    else:
        row.config_json = json.dumps(data)
        row.updated_at = datetime.now(UTC)


def get_provider_config(db: Session, provider: str) -> dict[str, str]:
    provider = provider.lower()
    defaults = _default_configs().get(provider, {})
    row = db.get(ProviderConfig, provider)
    row_data = _load_row_data(row)
    result: dict[str, str] = {}

    keys = set(defaults) | set(row_data)
    migrated = False

    for key in keys:
        default_value = str(defaults.get(key, ""))
        row_has_key = key in row_data
        row_value = str(row_data.get(key, ""))

        if not _is_secret(key):
            result[key] = row_value if key in row_data else default_value
            continue

        secret_value = keychain.get_secret(provider, key)
        if secret_value:
            result[key] = secret_value
            if row_value:
                row_data.pop(key, None)
                migrated = True
            continue

        if row_value:
            if keychain.set_secret(provider, key, row_value):
                result[key] = row_value
                row_data.pop(key, None)
                migrated = True
            else:
                result[key] = row_value
            continue

        if row_has_key:
            result[key] = row_value
        else:
            result[key] = default_value

    if migrated:
        _save_row_data(db, provider, row_data)
        db.commit()

    return result


def list_provider_configs(db: Session) -> dict[str, dict[str, str]]:
    return {provider: get_provider_config(db, provider) for provider in SUPPORTED_PROVIDERS}


def keychain_status() -> dict[str, str | bool]:
    backend = keychain.backend_name()
    return {
        "backend": backend,
        "available": keychain.is_available(),
    }


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
    row_data = _load_row_data(row)
    defaults = _default_configs().get(provider, {})

    for key, value in values.items():
        value = str(value)
        if _is_secret(key):
            if value == _CLEAR_SENTINEL:
                keychain.delete_secret(provider, key)
                row_data[key] = ""
                continue
            if not value or _looks_masked(value):
                continue
            if keychain.set_secret(provider, key, value):
                row_data.pop(key, None)
            else:
                row_data[key] = value
            continue
        row_data[key] = value

    # Keep non-secret defaults available, but do not persist secret defaults into SQLite.
    for key, default_value in defaults.items():
        if _is_secret(key):
            continue
        row_data.setdefault(key, default_value)

    _save_row_data(db, provider, row_data)
    db.commit()
    return get_provider_config(db, provider)
