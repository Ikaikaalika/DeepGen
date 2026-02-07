from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from deepgen.db import get_db
from deepgen.models import Person, UploadSession
from deepgen.schemas import (
    LivingConsentRequest,
    LivingPersonView,
    UploadSummary,
)
from deepgen.services.gedcom import export_gedcom, parse_gedcom_text
from deepgen.services.research import gap_candidates

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
DATA_DIR = Path("data/uploads")


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload", response_model=UploadSummary)
async def upload_gedcom(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadSummary:
    if not file.filename.lower().endswith((".ged", ".gedcom", ".txt")):
        raise HTTPException(status_code=400, detail="Expected a GEDCOM file")
    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = content_bytes.decode("latin-1", errors="ignore")

    parsed = parse_gedcom_text(content)
    session_id = uuid4().hex[:12]
    _ensure_data_dir()
    file_path = DATA_DIR / f"{session_id}.ged"
    file_path.write_text(content, encoding="utf-8")

    upload_session = UploadSession(
        id=session_id,
        filename=file.filename,
        gedcom_version=parsed.version,
    )
    db.add(upload_session)
    db.flush()

    living_count = 0
    living_pending_count = 0
    for person in parsed.people:
        is_living = person.is_living
        can_use_data = not is_living
        can_llm_research = not is_living
        if is_living:
            living_count += 1
            living_pending_count += 1
        db.add(
            Person(
                session_id=session_id,
                xref=person.xref,
                name=person.name,
                sex=person.sex,
                birth_date=person.birth_date,
                death_date=person.death_date,
                birth_year=person.birth_year,
                is_living=is_living,
                can_use_data=can_use_data,
                can_llm_research=can_llm_research,
                father_xref=person.father_xref,
                mother_xref=person.mother_xref,
            )
        )
    db.commit()
    return UploadSummary(
        session_id=session_id,
        filename=file.filename,
        gedcom_version=parsed.version,
        person_count=len(parsed.people),
        living_count=living_count,
        living_pending_count=living_pending_count,
    )


@router.get("/{session_id}/living-people", response_model=list[LivingPersonView])
def living_people(session_id: str, db: Session = Depends(get_db)) -> list[LivingPersonView]:
    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    stmt: Select[tuple[Person]] = (
        select(Person)
        .where(Person.session_id == session_id, Person.is_living.is_(True))
        .order_by(Person.name)
    )
    people = db.scalars(stmt).all()
    return [
        LivingPersonView(
            id=person.id,
            xref=person.xref,
            name=person.name,
            birth_date=person.birth_date,
            can_use_data=person.can_use_data,
            can_llm_research=person.can_llm_research,
        )
        for person in people
    ]


@router.post("/{session_id}/living-consent", response_model=list[LivingPersonView])
def update_living_consent(
    session_id: str,
    body: LivingConsentRequest,
    db: Session = Depends(get_db),
) -> list[LivingPersonView]:
    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.mark_all:
        stmt_all: Select[tuple[Person]] = select(Person).where(
            Person.session_id == session_id,
            Person.is_living.is_(True),
        )
        for person in db.scalars(stmt_all).all():
            person.can_use_data = body.mark_all.can_use_data
            person.can_llm_research = body.mark_all.can_llm_research

    for update in body.updates:
        person = db.get(Person, update.person_id)
        if not person or person.session_id != session_id or not person.is_living:
            continue
        person.can_use_data = update.can_use_data
        person.can_llm_research = update.can_llm_research

    db.commit()
    return living_people(session_id=session_id, db=db)


@router.get("/{session_id}/gaps")
def missing_ancestor_gaps(session_id: str, db: Session = Depends(get_db)):
    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return gap_candidates(db, session_id)


@router.get("/{session_id}/export", response_class=PlainTextResponse)
def export_session_gedcom(
    session_id: str,
    version: str = "7.0",
    db: Session = Depends(get_db),
) -> str:
    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if version not in {"5.5.1", "7.0"}:
        raise HTTPException(status_code=400, detail="Version must be 5.5.1 or 7.0")

    stmt: Select[tuple[Person]] = select(Person).where(Person.session_id == session_id).order_by(Person.id)
    people = db.scalars(stmt).all()
    payload = [
        {
            "xref": person.xref,
            "name": person.name,
            "sex": person.sex,
            "birth_date": person.birth_date,
            "death_date": person.death_date,
            "father_xref": person.father_xref,
            "mother_xref": person.mother_xref,
        }
        for person in people
    ]
    return export_gedcom(version=version, people=payload)
