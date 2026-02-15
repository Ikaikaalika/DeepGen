from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from deepgen.models import Person
from deepgen.schemas import GapCandidate


def gap_candidates(db: Session, session_id: str) -> list[GapCandidate]:
    """Return consent-safe missing-parent candidates in deterministic order."""

    stmt: Select[tuple[Person]] = select(Person).where(Person.session_id == session_id).order_by(Person.id)
    people = db.scalars(stmt).all()

    results: list[GapCandidate] = []
    for person in people:
        missing_father = not bool(person.father_xref)
        missing_mother = not bool(person.mother_xref)
        if not (missing_father or missing_mother):
            continue
        if person.is_living and not (person.can_use_data and person.can_llm_research):
            continue
        results.append(
            GapCandidate(
                person_id=person.id,
                xref=person.xref,
                name=person.name,
                missing_father=missing_father,
                missing_mother=missing_mother,
            )
        )

    return results
