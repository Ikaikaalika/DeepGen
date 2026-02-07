from pathlib import Path

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
from deepgen.services.provider_config import list_provider_configs

app = FastAPI(title=get_settings().app_name)
templates = Jinja2Templates(directory="deepgen/templates")
app.mount("/static", StaticFiles(directory="deepgen/static"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    Path("data/uploads").mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        name="index.html",
        context={"request": request},
    )


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    mlx_ready = True
    try:
        import mlx_lm  # noqa: F401
    except ImportError:
        mlx_ready = False
    configs = list_provider_configs(db)
    return {
        "status": "ok",
        "mlx_installed": mlx_ready,
        "llm_backend": configs.get("llm", {}).get("backend", "openai"),
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
