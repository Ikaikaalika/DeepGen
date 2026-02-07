from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from deepgen.db import get_db
from deepgen.schemas import ProviderConfigUpdate, ProviderConfigView
from deepgen.services.provider_config import (
    SUPPORTED_PROVIDERS,
    get_provider_config,
    list_provider_configs_masked,
    update_provider_config,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/config", response_model=list[ProviderConfigView])
def list_configs(db: Session = Depends(get_db)) -> list[ProviderConfigView]:
    configs = list_provider_configs_masked(db)
    return [ProviderConfigView(provider=k, values=v) for k, v in configs.items()]


@router.get("/config/{provider}", response_model=ProviderConfigView)
def get_config(provider: str, db: Session = Depends(get_db)) -> ProviderConfigView:
    provider = provider.lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unsupported provider")
    values = get_provider_config(db, provider)
    masked = {}
    for key, value in values.items():
        if any(marker in key.lower() for marker in ("key", "secret", "token", "password")) and value:
            masked[key] = f"{'*' * max(len(value) - 4, 0)}{value[-4:]}"
        else:
            masked[key] = value
    return ProviderConfigView(provider=provider, values=masked)


@router.put("/config/{provider}", response_model=ProviderConfigView)
def put_config(
    provider: str,
    body: ProviderConfigUpdate,
    db: Session = Depends(get_db),
) -> ProviderConfigView:
    provider = provider.lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unsupported provider")
    values = update_provider_config(db, provider, body.values)
    masked = {}
    for key, value in values.items():
        if any(marker in key.lower() for marker in ("key", "secret", "token", "password")) and value:
            masked[key] = f"{'*' * max(len(value) - 4, 0)}{value[-4:]}"
        else:
            masked[key] = value
    return ProviderConfigView(provider=provider, values=masked)
