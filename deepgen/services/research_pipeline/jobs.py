from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from deepgen.models import (
    EvidenceItem,
    ExtractedClaim,
    ParentProposal,
    Person,
    ProposalDecision,
    ResearchJob,
    ResearchQuestion,
)
from deepgen.schemas import ProposalDecisionRequest, ResearchQuestionAnswerRequest
from deepgen.services.connectors import SourceConnector, build_connectors
from deepgen.services.document_index import search_uploaded_documents_for_person
from deepgen.services.provider_config import list_provider_configs
from deepgen.services.research_pipeline.backend_adapters import resolve_runtime
from deepgen.services.research_pipeline.contradictions import evaluate_contradictions
from deepgen.services.research_pipeline.extraction import extract_claims_for_person
from deepgen.services.research_pipeline.retrieval import retrieve_evidence
from deepgen.services.research_pipeline.scoring import synthesize_proposals


def _now() -> datetime:
    return datetime.now(UTC)


def _load_stage_stats(job: ResearchJob) -> dict:
    try:
        payload = json.loads(job.stage_stats_json)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("person_xrefs", [])
    payload.setdefault("connector_overrides", {})
    payload.setdefault("errors", [])
    payload.setdefault("stage_durations_ms", {})
    payload.setdefault("backend_stats", {})
    return payload


def _save_stage_stats(job: ResearchJob, stats: dict) -> None:
    job.stage_stats_json = json.dumps(stats, sort_keys=True)


def _append_error(stats: dict, value: str) -> None:
    errors = stats.setdefault("errors", [])
    errors.append(value)


def _record_stage_duration(stats: dict, stage: str, elapsed_seconds: float) -> None:
    durations = stats.setdefault("stage_durations_ms", {})
    durations[stage] = int(durations.get(stage, 0) + (elapsed_seconds * 1000))


def _select_candidates(
    db: Session,
    session_id: str,
    people_xrefs: list[str] | None,
    max_people: int,
) -> list[str]:
    stmt: Select[tuple[Person]] = select(Person).where(Person.session_id == session_id).order_by(Person.id)
    people = db.scalars(stmt).all()

    selected: list[str] = []
    for person in people:
        if people_xrefs and person.xref not in people_xrefs:
            continue
        if person.father_xref and person.mother_xref:
            continue
        if person.is_living and not (person.can_use_data and person.can_llm_research):
            continue
        selected.append(person.xref)
        if len(selected) >= max_people:
            break
    return selected


def create_research_job(
    db: Session,
    *,
    session_id: str,
    people_xrefs: list[str] | None,
    max_people: int,
    connector_overrides: dict[str, bool] | None,
    prompt_template_version: str,
) -> ResearchJob:
    selected_xrefs = _select_candidates(
        db=db,
        session_id=session_id,
        people_xrefs=people_xrefs,
        max_people=max_people,
    )

    job = ResearchJob(
        id=uuid4().hex[:12],
        session_id=session_id,
        status="queued",
        stage="queued",
        target_count=len(selected_xrefs),
        prompt_template_version=prompt_template_version,
        stage_stats_json=json.dumps(
            {
                "person_xrefs": selected_xrefs,
                "connector_overrides": connector_overrides or {},
                "errors": [],
                "stage_durations_ms": {},
                "backend_stats": {},
            },
            sort_keys=True,
        ),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _filtered_connectors(connectors: list[SourceConnector], overrides: dict[str, bool]) -> list[SourceConnector]:
    if not overrides:
        return connectors
    filtered = [connector for connector in connectors if overrides.get(connector.name, True)]
    return filtered


def _create_question_if_missing(
    db: Session,
    *,
    job: ResearchJob,
    person_xref: str,
    relationship: str,
    question: str,
    rationale: str,
) -> None:
    existing = db.scalars(
        select(ResearchQuestion).where(
            ResearchQuestion.job_id == job.id,
            ResearchQuestion.person_xref == person_xref,
            ResearchQuestion.relationship == relationship,
            ResearchQuestion.question == question,
        )
    ).first()
    if existing:
        return

    db.add(
        ResearchQuestion(
            job_id=job.id,
            session_id=job.session_id,
            person_xref=person_xref,
            relationship=relationship,
            status="pending",
            question=question,
            rationale=rationale,
        )
    )


def _create_gap_questions_for_person(
    db: Session,
    *,
    job: ResearchJob,
    person: Person,
    drafts: list,
    contradiction_flags: list[str],
) -> None:
    for draft in drafts:
        if draft.relationship not in {"father", "mother"}:
            continue
        if draft.candidate_name:
            continue

        relationship_label = "father" if draft.relationship == "father" else "mother"
        _create_question_if_missing(
            db,
            job=job,
            person_xref=person.xref,
            relationship=draft.relationship,
            question=(
                f"For {person.name} ({person.xref}), do you know any likely {relationship_label} name, "
                "nickname, or surname variant?"
            ),
            rationale="Model found insufficient evidence for this parent relationship.",
        )
        _create_question_if_missing(
            db,
            job=job,
            person_xref=person.xref,
            relationship=draft.relationship,
            question=(
                f"Do you have any records for {person.name} ({person.xref}) that mention their {relationship_label} "
                "(census, obituary, church, military, or newspaper)?"
            ),
            rationale="Additional records may unlock parent attribution confidence.",
        )
        _create_question_if_missing(
            db,
            job=job,
            person_xref=person.xref,
            relationship=draft.relationship,
            question=(
                f"Are there living relatives, local historians, or social-media contacts you can reach "
                f"who may know {person.name}'s {relationship_label}?"
            ),
            rationale="Human contact leads can provide non-indexed family knowledge.",
        )

    if contradiction_flags:
        _create_question_if_missing(
            db,
            job=job,
            person_xref=person.xref,
            relationship="general",
            question=(
                f"There are conflicting parent leads for {person.name} ({person.xref}). "
                "Which candidate is most credible and why?"
            ),
            rationale=f"Contradictions detected: {', '.join(contradiction_flags)}",
        )


def _answered_questions_for_person(db: Session, *, session_id: str, person_xref: str) -> list[ResearchQuestion]:
    rows = db.scalars(
        select(ResearchQuestion)
        .where(
            ResearchQuestion.session_id == session_id,
            ResearchQuestion.person_xref == person_xref,
            ResearchQuestion.status == "answered",
        )
        .order_by(ResearchQuestion.updated_at.desc(), ResearchQuestion.id.desc())
        .limit(8)
    ).all()
    return rows


def run_research_job(db: Session, job_id: str) -> ResearchJob:
    job = db.get(ResearchJob, job_id)
    if not job:
        raise ValueError("Research job not found")

    if job.status == "completed":
        return job

    job.status = "running"
    job.stage = "initializing"
    job.started_at = job.started_at or _now()

    stats = _load_stage_stats(job)
    _save_stage_stats(job, stats)
    db.commit()

    try:
        configs = list_provider_configs(db)
        runtime = resolve_runtime(configs)
        connectors = _filtered_connectors(build_connectors(configs), stats.get("connector_overrides", {}))

        job.llm_backend = runtime.backend
        job.llm_model = runtime.model
        db.commit()

        xrefs: list[str] = [str(item) for item in stats.get("person_xrefs", [])]
        if not xrefs:
            xrefs = _select_candidates(db, job.session_id, None, max_people=10)

        people = db.scalars(
            select(Person).where(Person.session_id == job.session_id, Person.xref.in_(xrefs)).order_by(Person.id)
        ).all()

        if not people:
            job.status = "completed"
            job.stage = "completed"
            job.progress = 100.0
            job.finished_at = _now()
            _save_stage_stats(job, stats)
            db.commit()
            db.refresh(job)
            return job

        for idx, person in enumerate(people, start=1):
            retrieval_start = perf_counter()
            job.stage = "retrieval"
            retrieval = retrieve_evidence(
                connectors=connectors,
                name=person.name,
                birth_year=person.birth_year,
                max_retries=1,
                max_parallel_connectors=4,
            )
            uploaded_hits = search_uploaded_documents_for_person(
                db,
                session_id=job.session_id,
                name=person.name,
                birth_year=person.birth_year,
                limit=6,
            )
            answered_questions = _answered_questions_for_person(
                db,
                session_id=job.session_id,
                person_xref=person.xref,
            )
            _record_stage_duration(stats, "retrieval", perf_counter() - retrieval_start)
            job.retry_count += retrieval.retries_used
            for err in retrieval.errors:
                _append_error(stats, f"{person.xref} retrieval: {err}")

            evidence_rows: list[EvidenceItem] = []
            if not retrieval.evidence:
                fallback = EvidenceItem(
                    job_id=job.id,
                    person_xref=person.xref,
                    source="system",
                    title="No evidence found",
                    url="",
                    note="No configured connector returned evidence.",
                    normalized_url="",
                    normalized_title_hash="no-evidence",
                    retrieval_rank=0,
                )
                db.add(fallback)
                db.flush()
                evidence_rows.append(fallback)

            rank = 1
            for item in retrieval.evidence:
                row = EvidenceItem(
                    job_id=job.id,
                    person_xref=person.xref,
                    source=item.source,
                    title=item.title,
                    url=item.url,
                    note=item.note,
                    normalized_url=item.normalized_url,
                    normalized_title_hash=item.normalized_title_hash,
                    retrieval_rank=rank,
                )
                db.add(row)
                db.flush()
                evidence_rows.append(row)
                rank += 1

            for upload_item in uploaded_hits:
                row = EvidenceItem(
                    job_id=job.id,
                    person_xref=person.xref,
                    source=upload_item.source,
                    title=upload_item.title,
                    url=upload_item.url,
                    note=upload_item.note,
                    normalized_url=upload_item.url.strip().lower(),
                    normalized_title_hash=f"user-upload-{rank}",
                    retrieval_rank=rank,
                )
                db.add(row)
                db.flush()
                evidence_rows.append(row)
                rank += 1

            for answered in answered_questions:
                answer_text = (answered.answer or "").strip()
                if not answer_text:
                    continue
                question_text = answered.question.strip()
                row = EvidenceItem(
                    job_id=job.id,
                    person_xref=person.xref,
                    source="user_answers",
                    title=f"User answer ({answered.relationship})",
                    url="",
                    note=f"Q: {question_text} | A: {answer_text}",
                    normalized_url="",
                    normalized_title_hash=f"user-answer-{answered.id}",
                    retrieval_rank=rank,
                )
                db.add(row)
                db.flush()
                evidence_rows.append(row)
                rank += 1

            extraction_start = perf_counter()
            job.stage = "extraction"
            extraction = extract_claims_for_person(
                llm_client=runtime.client,
                person=person,
                evidence_items=evidence_rows,
                prompt_template_version=job.prompt_template_version,
            )
            _record_stage_duration(stats, "extraction", perf_counter() - extraction_start)
            job.retry_count += extraction.retries_used
            job.parse_repair_count += extraction.repairs_used
            for err in extraction.errors:
                _append_error(stats, f"{person.xref} extraction: {err}")

            contradiction_start = perf_counter()
            job.stage = "verification"
            contradictions = evaluate_contradictions(person=person, claims=extraction.claims)
            _record_stage_duration(stats, "verification", perf_counter() - contradiction_start)

            evidence_sources = {row.id: row.source for row in evidence_rows}

            synth_start = perf_counter()
            job.stage = "synthesis"
            drafts = synthesize_proposals(
                claims=extraction.claims,
                evidence_sources=evidence_sources,
                contradictions=contradictions,
            )
            _record_stage_duration(stats, "synthesis", perf_counter() - synth_start)

            for claim in extraction.claims:
                rel_flags = list(contradictions.by_relationship.get(claim.relationship, []))
                rel_flags.extend(contradictions.global_flags)
                rel_flags = sorted(set(rel_flags))
                db.add(
                    ExtractedClaim(
                        job_id=job.id,
                        person_xref=person.xref,
                        relationship=claim.relationship,
                        candidate_name=claim.candidate_name,
                        confidence=claim.confidence,
                        rationale=claim.rationale,
                        evidence_ids_json=json.dumps(claim.evidence_ids),
                        contradiction_flags_json=json.dumps(rel_flags),
                        score=0.0,
                        parse_valid=extraction.parse_valid,
                        raw_json=extraction.raw_text[:6000],
                    )
                )

            for draft in drafts:
                db.add(
                    ParentProposal(
                        job_id=job.id,
                        session_id=job.session_id,
                        person_xref=person.xref,
                        relationship=draft.relationship,
                        candidate_name=draft.candidate_name,
                        confidence=draft.confidence,
                        status=draft.status,
                        notes=draft.notes,
                        evidence_ids_json=json.dumps(draft.evidence_ids),
                        contradiction_flags_json=json.dumps(draft.contradiction_flags),
                        score_components_json=json.dumps(draft.score_components, sort_keys=True),
                    )
                )

            contradiction_flags: list[str] = []
            contradiction_flags.extend(contradictions.global_flags)
            for rel_flags in contradictions.by_relationship.values():
                contradiction_flags.extend(rel_flags)
            _create_gap_questions_for_person(
                db,
                job=job,
                person=person,
                drafts=drafts,
                contradiction_flags=sorted(set(contradiction_flags)),
            )

            if retrieval.errors or not extraction.parse_valid:
                job.error_count += 1

            job.completed_count = idx
            job.progress = round((idx / max(1, len(people))) * 100.0, 2)
            _save_stage_stats(job, stats)
            db.commit()

        job.status = "completed"
        job.stage = "completed"
        job.progress = 100.0
        job.finished_at = _now()
        _save_stage_stats(job, stats)
        db.commit()
        db.refresh(job)
        return job

    except Exception as exc:  # noqa: BLE001
        stats = _load_stage_stats(job)
        _append_error(stats, f"fatal: {exc}")
        job.status = "failed"
        job.stage = "failed"
        job.last_error = str(exc)
        job.finished_at = _now()
        _save_stage_stats(job, stats)
        db.commit()
        db.refresh(job)
        return job


def job_status_payload(job: ResearchJob) -> dict:
    stats = _load_stage_stats(job)
    return {
        "job_id": job.id,
        "session_id": job.session_id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "target_count": job.target_count,
        "completed_count": job.completed_count,
        "error_count": job.error_count,
        "retry_count": job.retry_count,
        "parse_repair_count": job.parse_repair_count,
        "prompt_template_version": job.prompt_template_version,
        "llm_backend": job.llm_backend,
        "llm_model": job.llm_model,
        "stage_durations_ms": stats.get("stage_durations_ms", {}),
        "errors": stats.get("errors", []),
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def _json_load_list(value: str) -> list:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _json_load_dict(value: str) -> dict:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def list_job_findings(db: Session, job_id: str) -> list[dict]:
    job = db.get(ResearchJob, job_id)
    if not job:
        raise ValueError("Research job not found")

    stats = _load_stage_stats(job)
    person_xrefs: list[str] = [str(item) for item in stats.get("person_xrefs", [])]

    people_by_xref = {
        person.xref: person
        for person in db.scalars(
            select(Person).where(Person.session_id == job.session_id, Person.xref.in_(person_xrefs))
        ).all()
    }

    findings: list[dict] = []
    for person_xref in person_xrefs:
        evidence_rows = db.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.job_id == job.id, EvidenceItem.person_xref == person_xref)
            .order_by(EvidenceItem.retrieval_rank, EvidenceItem.id)
        ).all()
        proposal_rows = db.scalars(
            select(ParentProposal)
            .where(ParentProposal.job_id == job.id, ParentProposal.person_xref == person_xref)
            .order_by(ParentProposal.id)
        ).all()

        contradiction_flags: set[str] = set()
        score_breakdown: dict[str, dict] = {}
        proposal_ids: list[int] = []

        for proposal in proposal_rows:
            contradiction_flags.update(_json_load_list(proposal.contradiction_flags_json))
            score_breakdown[proposal.relationship] = _json_load_dict(proposal.score_components_json)
            proposal_ids.append(proposal.id)

        findings.append(
            {
                "person_xref": person_xref,
                "person_name": people_by_xref.get(person_xref).name if people_by_xref.get(person_xref) else person_xref,
                "summary": "Research findings generated for manual review.",
                "evidence_ids": [item.id for item in evidence_rows],
                "evidence": [
                    {
                        "id": item.id,
                        "source": item.source,
                        "title": item.title,
                        "url": item.url,
                        "note": item.note,
                    }
                    for item in evidence_rows
                ],
                "contradiction_flags": sorted(contradiction_flags),
                "score_breakdown": score_breakdown,
                "proposal_ids": proposal_ids,
            }
        )

    return findings


def list_job_proposals(db: Session, job_id: str, *, limit: int, offset: int) -> tuple[list[dict], int]:
    job = db.get(ResearchJob, job_id)
    if not job:
        raise ValueError("Research job not found")

    total = int(
        db.scalar(select(func.count()).select_from(ParentProposal).where(ParentProposal.job_id == job_id)) or 0
    )

    rows = db.scalars(
        select(ParentProposal)
        .where(ParentProposal.job_id == job_id)
        .order_by(ParentProposal.person_xref, ParentProposal.relationship, ParentProposal.id)
        .offset(offset)
        .limit(limit)
    ).all()

    payload: list[dict] = []
    for row in rows:
        payload.append(
            {
                "proposal_id": row.id,
                "job_id": row.job_id,
                "session_id": row.session_id,
                "person_xref": row.person_xref,
                "relationship": row.relationship,
                "candidate_name": row.candidate_name,
                "confidence": row.confidence,
                "status": row.status,
                "notes": row.notes,
                "evidence_ids": _json_load_list(row.evidence_ids_json),
                "contradiction_flags": _json_load_list(row.contradiction_flags_json),
                "score_components": _json_load_dict(row.score_components_json),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )

    return payload, total


def _question_to_payload(row: ResearchQuestion) -> dict:
    return {
        "question_id": row.id,
        "job_id": row.job_id,
        "session_id": row.session_id,
        "person_xref": row.person_xref,
        "relationship": row.relationship,
        "status": row.status,
        "question": row.question,
        "rationale": row.rationale,
        "answer": row.answer,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_job_questions(db: Session, job_id: str) -> tuple[list[dict], int]:
    job = db.get(ResearchJob, job_id)
    if not job:
        raise ValueError("Research job not found")

    rows = db.scalars(
        select(ResearchQuestion)
        .where(ResearchQuestion.job_id == job_id)
        .order_by(ResearchQuestion.status, ResearchQuestion.person_xref, ResearchQuestion.id)
    ).all()
    payload = [_question_to_payload(row) for row in rows]
    return payload, len(payload)


def answer_research_question(
    db: Session,
    question_id: int,
    body: ResearchQuestionAnswerRequest,
) -> ResearchQuestion:
    row = db.get(ResearchQuestion, question_id)
    if not row:
        raise ValueError("Research question not found")

    if body.status == "answered":
        answer = (body.answer or "").strip()
        if not answer:
            raise ValueError("Answer is required when status is 'answered'")
        row.answer = answer
        row.status = "answered"
    elif body.status == "skipped":
        row.status = "skipped"
    else:
        raise ValueError(f"Unsupported status: {body.status}")

    db.commit()
    db.refresh(row)
    return row


def decide_proposal(db: Session, proposal_id: int, body: ProposalDecisionRequest) -> ParentProposal:
    proposal = db.get(ParentProposal, proposal_id)
    if not proposal:
        raise ValueError("Proposal not found")

    payload = body.model_dump(exclude_none=True)
    action = body.action

    if action == "approve":
        evidence_ids = _json_load_list(proposal.evidence_ids_json)
        if not evidence_ids:
            raise ValueError("Cannot approve proposal without citations")
        if not proposal.candidate_name:
            raise ValueError("Cannot approve proposal without candidate_name")
        proposal.status = "approved"
    elif action == "reject":
        proposal.status = "rejected"
    elif action == "edit":
        if body.candidate_name is not None:
            cleaned = body.candidate_name.strip()
            proposal.candidate_name = cleaned or None
        if body.confidence is not None:
            proposal.confidence = max(0.0, min(1.0, float(body.confidence)))
        if body.notes is not None:
            proposal.notes = body.notes
        proposal.status = "pending_review"
    else:
        raise ValueError(f"Unsupported action: {action}")

    db.add(
        ProposalDecision(
            proposal_id=proposal.id,
            action=action,
            decided_by="user",
            notes=body.notes or "",
            payload_json=json.dumps(payload, sort_keys=True),
        )
    )
    db.commit()
    db.refresh(proposal)
    return proposal
