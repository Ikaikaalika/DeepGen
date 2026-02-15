from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deepgen.services.source_types import SourceResult

TEXT_EXTENSIONS = {".txt", ".md", ".ged", ".gedcom", ".csv", ".json"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".webp", ".heic"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | {".pdf"}


class LocalFolderError(RuntimeError):
    pass


@dataclass
class LocalFolderIndex:
    folder_path: str
    file_count: int
    sample_files: list[str]


def _resolve_folder(folder_path: str) -> Path:
    folder = Path(folder_path).expanduser().resolve()
    if not folder.exists():
        raise LocalFolderError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise LocalFolderError(f"Path is not a folder: {folder}")
    return folder


def index_local_folder(folder_path: str, max_files: int = 2000) -> LocalFolderIndex:
    folder = _resolve_folder(folder_path)
    files: list[str] = []
    for path in folder.rglob("*"):
        if len(files) >= max_files:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        files.append(str(path))
    files.sort()
    return LocalFolderIndex(
        folder_path=str(folder),
        file_count=len(files),
        sample_files=files[:25],
    )


def _read_snippet(path: Path, max_chars: int = 400) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return "Binary or image file; text extraction skipped."
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "Unable to read file content."
    compact = " ".join(data.split())
    return compact[:max_chars] if compact else "No readable text."


def search_local_records(
    folder_path: str,
    name: str,
    birth_year: int | None,
    max_results: int = 6,
) -> list[SourceResult]:
    folder = _resolve_folder(folder_path)
    tokens = [token.lower() for token in name.split() if token.strip()]
    year_token = str(birth_year) if birth_year else ""

    hits: list[SourceResult] = []
    for path in folder.rglob("*"):
        if len(hits) >= max_results:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        haystack = f"{path.name.lower()} {str(path.parent).lower()}"
        name_match = all(token in haystack for token in tokens[:2]) if tokens else False
        year_match = bool(year_token and year_token in haystack)
        if not name_match and not year_match:
            continue

        snippet = _read_snippet(path)
        note = f"Local file match. Birth year hint: {birth_year or 'unknown'}."
        hits.append(
            SourceResult(
                source="local_folder",
                title=path.name,
                url=path.as_uri(),
                note=f"{note} Snippet: {snippet}",
            )
        )
    return hits
