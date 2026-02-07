from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from deepgen.models import Person
from deepgen.schemas import GapCandidate, PersonProposal, ResearchFinding
from deepgen.services.connectors import SourceConnector
from deepgen.services.llm import LLMClient


def gap_candidates(db: Session, session_id: str) -> list[GapCandidate]:
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


def _build_prompt(person: Person, source_lines: list[str]) -> str:
    return (
        "Given a genealogy profile with missing parents, propose likely ancestor leads.\n"
        f"Person: {person.name}\n"
        f"XREF: {person.xref}\n"
        f"Birth: {person.birth_date or 'unknown'}\n"
        f"Death: {person.death_date or 'unknown'}\n"
        f"Sex: {person.sex or 'unknown'}\n"
        "Source hints:\n"
        + "\n".join(source_lines)
        + "\nReturn a concise summary and explicit father/mother candidate names if present."
    )


def run_research(
    db: Session,
    session_id: str,
    people_xrefs: list[str] | None,
    max_people: int,
    connectors: list[SourceConnector],
    llm_client: LLMClient | None,
) -> list[ResearchFinding]:
    stmt: Select[tuple[Person]] = select(Person).where(Person.session_id == session_id).order_by(Person.id)
    people = db.scalars(stmt).all()
    selected: list[Person] = []
    for person in people:
        if people_xrefs and person.xref not in people_xrefs:
            continue
        if not (not person.father_xref or not person.mother_xref):
            continue
        if person.is_living and not (person.can_use_data and person.can_llm_research):
            continue
        selected.append(person)
    selected = selected[:max_people]

    findings: list[ResearchFinding] = []
    for person in selected:
        source_results = []
        for connector in connectors:
            source_results.extend(connector.search_person(person.name, person.birth_year))
        source_lines = [
            f"- [{item.source}] {item.title}: {item.url} ({item.note})" for item in source_results
        ]
        if not source_lines:
            source_lines = ["- No configured source connectors available."]

        summary = "LLM disabled or missing API credentials."
        proposals: list[PersonProposal] = []
        if llm_client:
            prompt = _build_prompt(person, source_lines)
            try:
                summary = llm_client.generate(prompt)
            except Exception as exc:  # noqa: BLE001
                summary = f"LLM research failed: {exc}"

        if not person.father_xref:
            proposals.append(
                PersonProposal(
                    name="Unknown Father Candidate",
                    relationship="father",
                    confidence=0.2,
                    notes="Placeholder. Replace with extracted name from source evidence.",
                )
            )
        if not person.mother_xref:
            proposals.append(
                PersonProposal(
                    name="Unknown Mother Candidate",
                    relationship="mother",
                    confidence=0.2,
                    notes="Placeholder. Replace with extracted name from source evidence.",
                )
            )

        findings.append(
            ResearchFinding(
                person_xref=person.xref,
                person_name=person.name,
                summary=summary,
                proposals=proposals,
            )
        )
    return findings
