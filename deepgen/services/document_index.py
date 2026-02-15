from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from deepgen.models import IndexedDocument
from deepgen.services.source_types import SourceResult

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".ged", ".gedcom", ".log"}
UPLOAD_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".heic"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class DocumentIndexError(RuntimeError):
    pass


def _documents_dir(session_id: str) -> Path:
    base = Path("data/uploads") / session_id / "documents"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.strip())
    cleaned = cleaned.strip("._")
    return cleaned or "upload.bin"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_text(content_bytes: bytes, path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in TEXT_EXTENSIONS:
        return "Binary or non-text upload indexed by metadata only."

    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = content_bytes.decode("latin-1", errors="ignore")
    compact = " ".join(text.split())
    return compact[:10000]


def _build_indexed_text(filename: str, text_snippet: str) -> str:
    return f"{filename} {text_snippet}".strip().lower()


def index_uploaded_document(
    db: Session,
    *,
    session_id: str,
    filename: str,
    content_bytes: bytes,
    content_type: str,
) -> IndexedDocument:
    if not filename:
        raise DocumentIndexError("Missing filename")

    safe_name = _safe_filename(filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in UPLOAD_EXTENSIONS:
        raise DocumentIndexError(f"Unsupported upload type: {ext or 'unknown'}")

    size = len(content_bytes)
    if size <= 0:
        raise DocumentIndexError("Uploaded file is empty")
    if size > MAX_UPLOAD_BYTES:
        raise DocumentIndexError("Uploaded file exceeds max size of 25MB")

    digest = _sha256_bytes(content_bytes)
    existing = db.scalars(
        select(IndexedDocument).where(
            IndexedDocument.session_id == session_id,
            IndexedDocument.content_hash == digest,
        )
    ).first()
    if existing:
        return existing

    doc_dir = _documents_dir(session_id)
    stored_name = f"{uuid4().hex[:8]}_{safe_name}"
    stored_path = doc_dir / stored_name
    stored_path.write_bytes(content_bytes)

    text_snippet = _extract_text(content_bytes, stored_path)
    indexed_text = _build_indexed_text(filename=safe_name, text_snippet=text_snippet)

    row = IndexedDocument(
        session_id=session_id,
        original_filename=safe_name,
        stored_path=str(stored_path.resolve()),
        mime_type=content_type or "",
        size_bytes=size,
        content_hash=digest,
        source="user_upload",
        text_snippet=text_snippet[:2000],
        indexed_text=indexed_text,
        indexed_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_indexed_documents(
    db: Session,
    *,
    session_id: str,
    limit: int,
    offset: int,
) -> tuple[list[IndexedDocument], int]:
    total = int(
        db.scalar(
            select(func.count()).select_from(IndexedDocument).where(IndexedDocument.session_id == session_id)
        )
        or 0
    )

    rows = db.scalars(
        select(IndexedDocument)
        .where(IndexedDocument.session_id == session_id)
        .order_by(IndexedDocument.created_at.desc(), IndexedDocument.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return rows, total


def search_indexed_documents(
    db: Session,
    *,
    session_id: str,
    query: str,
    limit: int,
) -> list[IndexedDocument]:
    tokens = [token.lower() for token in query.split() if token.strip()]
    if not tokens:
        return []

    stmt: Select[tuple[IndexedDocument]] = select(IndexedDocument).where(IndexedDocument.session_id == session_id)
    candidates = db.scalars(stmt).all()

    scored: list[tuple[int, IndexedDocument]] = []
    for row in candidates:
        haystack = f"{row.original_filename.lower()} {row.indexed_text.lower()}"
        score = sum(1 for token in tokens if token in haystack)
        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda item: (item[0], item[1].indexed_at, item[1].id), reverse=True)
    return [row for _, row in scored[:limit]]


def reindex_session_documents(db: Session, *, session_id: str) -> dict[str, int]:
    rows = db.scalars(select(IndexedDocument).where(IndexedDocument.session_id == session_id)).all()
    indexed = 0
    skipped = 0

    for row in rows:
        path = Path(row.stored_path)
        if not path.exists() or not path.is_file():
            skipped += 1
            continue
        try:
            content_bytes = path.read_bytes()
        except OSError:
            skipped += 1
            continue

        text_snippet = _extract_text(content_bytes, path)
        row.text_snippet = text_snippet[:2000]
        row.indexed_text = _build_indexed_text(filename=row.original_filename, text_snippet=text_snippet)
        row.indexed_at = datetime.now(UTC)
        indexed += 1

    db.commit()
    return {"total": len(rows), "indexed": indexed, "skipped": skipped}


def search_uploaded_documents_for_person(
    db: Session,
    *,
    session_id: str,
    name: str,
    birth_year: int | None,
    limit: int = 5,
) -> list[SourceResult]:
    query = f"{name} {birth_year}" if birth_year else name
    rows = search_indexed_documents(db, session_id=session_id, query=query, limit=limit)

    results: list[SourceResult] = []
    for row in rows:
        url = ""
        try:
            path = Path(row.stored_path)
            if path.exists():
                url = path.as_uri()
        except ValueError:
            url = ""

        results.append(
            SourceResult(
                source="user_uploads",
                title=row.original_filename,
                url=url,
                note=(
                    "Indexed user upload match. "
                    f"Snippet: {row.text_snippet[:240]}"
                ),
            )
        )

    return results
