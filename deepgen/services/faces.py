from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deepgen.models import Person
from deepgen.services.local_files import IMAGE_EXTENSIONS


class FacePairingError(RuntimeError):
    pass


@dataclass
class FacePairResult:
    image_path: str
    person_xref: str
    person_name: str
    confidence: float
    distance: float


@dataclass
class FacePairingReport:
    engine: str
    scanned_images: int
    reference_faces: int
    pairs: list[FacePairResult]
    skipped_images: int


def _load_face_lib():
    try:
        import face_recognition  # type: ignore
        import numpy as np
    except ImportError as exc:
        raise FacePairingError(
            "face_recognition is not installed. Install with: pip install -e .[vision]"
        ) from exc
    return face_recognition, np


def _image_files(folder: Path, max_images: int) -> list[Path]:
    paths: list[Path] = []
    for path in folder.rglob("*"):
        if len(paths) >= max_images:
            break
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            paths.append(path)
    paths.sort()
    return paths


def _name_tokens(name: str) -> list[str]:
    return [token.lower() for token in name.replace("/", " ").split() if len(token) >= 3]


def pair_faces_to_people(
    folder_path: str,
    people: list[Person],
    max_images: int = 400,
    threshold: float = 0.52,
) -> FacePairingReport:
    face_recognition, np = _load_face_lib()

    folder = Path(folder_path).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise FacePairingError(f"Folder does not exist or is not a directory: {folder}")

    token_map: dict[int, list[str]] = {person.id: _name_tokens(person.name) for person in people}
    by_id: dict[int, Person] = {person.id: person for person in people}

    reference_encodings: dict[int, list] = {}
    unknown_images: list[tuple[Path, object]] = []
    scanned = 0
    skipped = 0

    for image_path in _image_files(folder, max_images=max_images):
        scanned += 1
        try:
            img = face_recognition.load_image_file(str(image_path))
            encodings = face_recognition.face_encodings(img)
        except Exception:
            skipped += 1
            continue
        if not encodings:
            skipped += 1
            continue

        encoding = encodings[0]
        filename = image_path.stem.lower()
        matched_person_id = None

        for person_id, tokens in token_map.items():
            if not tokens:
                continue
            matched_tokens = sum(1 for token in tokens[:2] if token in filename)
            if matched_tokens >= 1:
                matched_person_id = person_id
                break

        if matched_person_id is not None:
            reference_encodings.setdefault(matched_person_id, []).append(encoding)
        else:
            unknown_images.append((image_path, encoding))

    if not reference_encodings:
        raise FacePairingError(
            "No reference faces found. Add at least a few labeled images named with person names."
        )

    reference_centroids: dict[int, object] = {
        person_id: np.mean(encs, axis=0)
        for person_id, encs in reference_encodings.items()
        if encs
    }

    pairs: list[FacePairResult] = []
    for image_path, encoding in unknown_images:
        best_id = None
        best_distance = 9.0
        for person_id, centroid in reference_centroids.items():
            distance = float(np.linalg.norm(encoding - centroid))
            if distance < best_distance:
                best_id = person_id
                best_distance = distance

        if best_id is None or best_distance > threshold:
            continue

        person = by_id[best_id]
        confidence = max(0.0, min(1.0, 1.0 - best_distance))
        pairs.append(
            FacePairResult(
                image_path=str(image_path),
                person_xref=person.xref,
                person_name=person.name,
                confidence=round(confidence, 3),
                distance=round(best_distance, 3),
            )
        )

    pairs.sort(key=lambda item: item.confidence, reverse=True)
    return FacePairingReport(
        engine="face_recognition",
        scanned_images=scanned,
        reference_faces=sum(len(v) for v in reference_encodings.values()),
        pairs=pairs,
        skipped_images=skipped,
    )
