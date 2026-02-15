import os
from pathlib import Path
from importlib.util import find_spec

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from deepgen.config import get_settings
from deepgen.db import get_db, init_db
from deepgen.routers.config_router import router as config_router
from deepgen.routers.research_router import router as research_router
from deepgen.routers.sessions_router import router as sessions_router
from deepgen.services.ocr import run_ocr
from deepgen.services.provider_config import keychain_status, list_provider_configs
from deepgen.services.startup_checks import StartupCheckResult, run_startup_preflight
from deepgen.services.updater import check_for_updates
from deepgen.version import get_app_version

app = FastAPI(title=get_settings().app_name)
templates = Jinja2Templates(directory="deepgen/templates")
app.mount("/static", StaticFiles(directory="deepgen/static"), name="static")
STARTUP_RESULT = StartupCheckResult(ok=True, errors=[], warnings=[])


@app.on_event("startup")
def on_startup() -> None:
    global STARTUP_RESULT
    init_db()
    Path("data/uploads").mkdir(parents=True, exist_ok=True)
    STARTUP_RESULT = run_startup_preflight()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        name="index.html",
        context={"request": request},
    )


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    mlx_ready = bool(find_spec("mlx_lm"))
    vision_ready = bool(find_spec("face_recognition"))
    ocr_ready = bool(find_spec("pytesseract") and find_spec("PIL"))
    configs = list_provider_configs(db)
    kc = keychain_status()
    return {
        "status": "ok" if STARTUP_RESULT.ok else "degraded",
        "app_version": get_app_version(),
        "mlx_installed": mlx_ready,
        "vision_installed": vision_ready,
        "ocr_installed": ocr_ready,
        "llm_backend": configs.get("llm", {}).get("backend", "openai"),
        "keychain_backend": kc["backend"],
        "keychain_available": kc["available"],
        "research_v2_enabled": get_settings().research_v2_enabled,
        "startup_errors": STARTUP_RESULT.errors,
        "startup_warnings": STARTUP_RESULT.warnings,
    }


@app.get("/api/app/meta")
def app_meta():
    kc = keychain_status()
    return {
        "app_name": get_settings().app_name,
        "app_version": get_app_version(),
        "keychain_backend": kc["backend"],
        "keychain_available": kc["available"],
        "research_v2_enabled": get_settings().research_v2_enabled,
        "startup_ok": STARTUP_RESULT.ok,
        "startup_errors": STARTUP_RESULT.errors,
        "startup_warnings": STARTUP_RESULT.warnings,
    }


@app.get("/api/app/update-check")
def app_update_check():
    app_version = get_app_version()
    feed_url = os.getenv("DEEPGEN_UPDATE_FEED_URL", "").strip()
    if not feed_url:
        return {
            "enabled": False,
            "available": False,
            "current_version": app_version,
            "latest_version": app_version,
            "download_url": "",
            "notes": "Set DEEPGEN_UPDATE_FEED_URL to enable update checks.",
        }
    result = check_for_updates(current_version=app_version, feed_url=feed_url)
    return {
        "enabled": True,
        "available": result.available,
        "current_version": result.current_version,
        "latest_version": result.latest_version,
        "download_url": result.download_url,
        "notes": result.notes,
    }


@app.post("/api/ocr")
async def ocr_file(
    file: UploadFile = File(...),
    provider: str = "tesseract",
):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
        raise HTTPException(status_code=400, detail="Upload an image for OCR in this scaffold")
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / f"ocr_{file.filename}"
    temp_path.write_bytes(await file.read())
    text = run_ocr(temp_path, provider=provider)
    return {"provider": provider, "text": text}


app.include_router(config_router)
app.include_router(sessions_router)
app.include_router(research_router)
