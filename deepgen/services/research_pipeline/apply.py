from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from deepgen.models import ApplyAuditEvent, ParentProposal, Person


@dataclass
class ApplyResult:
    applied_updates: int
    skipped: list[dict[str, str]]


def _next_xref(db: Session, session_id: str) -> str:
    stmt: Select[tuple[Person]] = select(Person).where(Person.session_id == session_id)
    max_num = 0
    for person in db.scalars(stmt).all():
        xref = person.xref.strip()
        if xref.startswith("@I") and xref.endswith("@"):
            raw = xref[2:-1]
            if raw.isdigit():
                max_num = max(max_num, int(raw))
    return f"@I{max_num + 1}@"


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _is_name_match(existing_name: str, candidate_name: str) -> bool:
    left = _norm_name(existing_name)
    right = _norm_name(candidate_name)
    if not left or not right:
        return False
    if left == right:
        return True
    return SequenceMatcher(a=left, b=right).ratio() >= 0.93


def _find_existing_person(db: Session, session_id: str, candidate_name: str, sex: str) -> Person | None:
    stmt: Select[tuple[Person]] = select(Person).where(Person.session_id == session_id)
    for person in db.scalars(stmt).all():
        if person.sex and sex and person.sex != sex:
            continue
        if _is_name_match(person.name, candidate_name):
            return person
    return None


def _load_evidence_ids(raw: str) -> list[int]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    results: list[int] = []
    for item in payload:
        try:
            results.append(int(item))
        except (TypeError, ValueError):
            continue
    return results


def apply_approved_proposals(db: Session, session_id: str, *, job_id: str | None = None) -> ApplyResult:
    stmt: Select[tuple[ParentProposal]] = select(ParentProposal).where(
        ParentProposal.session_id == session_id,
        ParentProposal.status == "approved",
    )
    if job_id:
        stmt = stmt.where(ParentProposal.job_id == job_id)

    proposals = db.scalars(stmt.order_by(ParentProposal.id)).all()
    skipped: list[dict[str, str]] = []
    applied_updates = 0

    for proposal in proposals:
        relationship = proposal.relationship
        candidate_name = (proposal.candidate_name or "").strip()
        evidence_ids = _load_evidence_ids(proposal.evidence_ids_json)

        if not candidate_name:
            skipped.append({"proposal_id": str(proposal.id), "reason": "candidate_missing"})
            db.add(
                ApplyAuditEvent(
                    job_id=proposal.job_id,
                    session_id=session_id,
                    proposal_id=proposal.id,
                    child_xref=proposal.person_xref,
                    relationship=relationship,
                    action="skipped",
                    detail="Candidate name is empty.",
                )
            )
            continue

        if not evidence_ids:
            skipped.append({"proposal_id": str(proposal.id), "reason": "missing_citations"})
            db.add(
                ApplyAuditEvent(
                    job_id=proposal.job_id,
                    session_id=session_id,
                    proposal_id=proposal.id,
                    child_xref=proposal.person_xref,
                    relationship=relationship,
                    action="skipped",
                    detail="Proposal has no citations.",
                )
            )
            continue

        child = db.scalars(
            select(Person).where(Person.session_id == session_id, Person.xref == proposal.person_xref)
        ).first()
        if not child:
            skipped.append({"proposal_id": str(proposal.id), "reason": "child_not_found"})
            db.add(
                ApplyAuditEvent(
                    job_id=proposal.job_id,
                    session_id=session_id,
                    proposal_id=proposal.id,
                    child_xref=proposal.person_xref,
                    relationship=relationship,
                    action="skipped",
                    detail="Child not found in session.",
                )
            )
            continue

        if relationship == "father" and child.father_xref:
            skipped.append({"proposal_id": str(proposal.id), "reason": "father_already_set"})
            db.add(
                ApplyAuditEvent(
                    job_id=proposal.job_id,
                    session_id=session_id,
                    proposal_id=proposal.id,
                    child_xref=proposal.person_xref,
                    relationship=relationship,
                    action="skipped",
                    detail="Father is already linked.",
                )
            )
            continue

        if relationship == "mother" and child.mother_xref:
            skipped.append({"proposal_id": str(proposal.id), "reason": "mother_already_set"})
            db.add(
                ApplyAuditEvent(
                    job_id=proposal.job_id,
                    session_id=session_id,
                    proposal_id=proposal.id,
                    child_xref=proposal.person_xref,
                    relationship=relationship,
                    action="skipped",
                    detail="Mother is already linked.",
                )
            )
            continue

        expected_sex = "M" if relationship == "father" else "F"
        existing = _find_existing_person(db, session_id, candidate_name, expected_sex)
        created_xref: str | None = None

        if existing:
            parent_xref = existing.xref
        else:
            parent_xref = _next_xref(db, session_id)
            person = Person(
                session_id=session_id,
                xref=parent_xref,
                name=candidate_name,
                sex=expected_sex,
                is_living=False,
                can_use_data=True,
                can_llm_research=True,
            )
            db.add(person)
            db.flush()
            created_xref = person.xref

        if relationship == "father":
            child.father_xref = parent_xref
        else:
            child.mother_xref = parent_xref

        proposal.status = "applied"
        applied_updates += 1

        db.add(
            ApplyAuditEvent(
                job_id=proposal.job_id,
                session_id=session_id,
                proposal_id=proposal.id,
                child_xref=proposal.person_xref,
                relationship=relationship,
                action="applied",
                detail="Applied approved proposal.",
                created_person_xref=created_xref,
            )
        )

    db.commit()
    return ApplyResult(applied_updates=applied_updates, skipped=skipped)
