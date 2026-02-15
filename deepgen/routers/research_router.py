from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from deepgen.config import get_settings
from deepgen.db import get_db
from deepgen.models import ParentProposal, Person, ResearchJob, UploadSession
from deepgen.schemas import (
    ApplyApprovedRequest,
    ApplyApprovedResponse,
    FacePairMatch,
    FacePairRequest,
    FacePairResponse,
    LocalFolderIndexRequest,
    LocalFolderIndexResponse,
    ProposalDecisionRequest,
    ProposalDecisionResponse,
    ResearchFindingsResponse,
    ResearchJobCreateRequest,
    ResearchJobCreateResponse,
    ResearchJobStatusResponse,
    ResearchQuestionAnswerRequest,
    ResearchQuestionAnswerResponse,
    ResearchQuestionsResponse,
    ResearchQuestionView,
    ResearchProposalView,
    ResearchProposalsResponse,
)
from deepgen.services.faces import FacePairingError, pair_faces_to_people
from deepgen.services.local_files import LocalFolderError, index_local_folder
from deepgen.services.provider_config import list_provider_configs
from deepgen.services.research_pipeline.apply import apply_approved_proposals
from deepgen.services.research_pipeline.jobs import (
    answer_research_question,
    create_research_job,
    decide_proposal,
    job_status_payload,
    list_job_findings,
    list_job_proposals,
    list_job_questions,
    run_research_job,
)

router = APIRouter(tags=["research"])
sessions_router = APIRouter(prefix="/api/sessions", tags=["research"])
jobs_router = APIRouter(prefix="/api/research", tags=["research"])


def _assert_v2_enabled() -> None:
    if not get_settings().research_v2_enabled:
        raise HTTPException(status_code=404, detail="Research v2 endpoints are disabled")


def _proposal_json_to_view(row: ParentProposal) -> ResearchProposalView:
    def load_list(raw: str) -> list:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return payload if isinstance(payload, list) else []

    def load_dict(raw: str) -> dict:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    return ResearchProposalView(
        proposal_id=row.id,
        job_id=row.job_id,
        session_id=row.session_id,
        person_xref=row.person_xref,
        relationship=row.relationship,
        candidate_name=row.candidate_name,
        confidence=row.confidence,
        status=row.status,
        notes=row.notes,
        evidence_ids=load_list(row.evidence_ids_json),
        contradiction_flags=load_list(row.contradiction_flags_json),
        score_components=load_dict(row.score_components_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@sessions_router.post("/{session_id}/research/jobs", response_model=ResearchJobCreateResponse)
def create_session_research_job(
    session_id: str,
    body: ResearchJobCreateRequest,
    db: Session = Depends(get_db),
) -> ResearchJobCreateResponse:
    _assert_v2_enabled()

    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    max_people = max(1, min(body.max_people, 200))
    job = create_research_job(
        db=db,
        session_id=session_id,
        people_xrefs=body.person_xrefs,
        max_people=max_people,
        connector_overrides=body.connector_overrides,
        prompt_template_version=get_settings().research_prompt_template_version,
    )

    # Execute in-process for deterministic local behavior.
    run_research_job(db, job.id)

    return ResearchJobCreateResponse(
        job_id=job.id,
        status="queued",
        created_at=job.created_at,
    )


@jobs_router.get("/jobs/{job_id}", response_model=ResearchJobStatusResponse)
def get_research_job_status(
    job_id: str,
    db: Session = Depends(get_db),
) -> ResearchJobStatusResponse:
    _assert_v2_enabled()

    job = db.get(ResearchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")

    return ResearchJobStatusResponse(**job_status_payload(job))


@jobs_router.get("/jobs/{job_id}/findings", response_model=ResearchFindingsResponse)
def get_research_job_findings(
    job_id: str,
    db: Session = Depends(get_db),
) -> ResearchFindingsResponse:
    _assert_v2_enabled()

    try:
        findings = list_job_findings(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResearchFindingsResponse(job_id=job_id, findings=findings)


@jobs_router.get("/jobs/{job_id}/proposals", response_model=ResearchProposalsResponse)
def get_research_job_proposals(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ResearchProposalsResponse:
    _assert_v2_enabled()

    try:
        proposals, total = list_job_proposals(db, job_id, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ResearchProposalsResponse(
        job_id=job_id,
        total=total,
        limit=limit,
        offset=offset,
        proposals=proposals,
    )


@jobs_router.get("/jobs/{job_id}/questions", response_model=ResearchQuestionsResponse)
def get_research_job_questions(
    job_id: str,
    db: Session = Depends(get_db),
) -> ResearchQuestionsResponse:
    _assert_v2_enabled()

    try:
        questions, total = list_job_questions(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ResearchQuestionsResponse(
        job_id=job_id,
        total=total,
        questions=[ResearchQuestionView(**item) for item in questions],
    )


@jobs_router.post("/proposals/{proposal_id}/decision", response_model=ProposalDecisionResponse)
def decide_research_proposal(
    proposal_id: int,
    body: ProposalDecisionRequest,
    db: Session = Depends(get_db),
) -> ProposalDecisionResponse:
    _assert_v2_enabled()

    try:
        proposal = decide_proposal(db, proposal_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ProposalDecisionResponse(proposal=_proposal_json_to_view(proposal))


@jobs_router.post("/questions/{question_id}/answer", response_model=ResearchQuestionAnswerResponse)
def answer_job_question(
    question_id: int,
    body: ResearchQuestionAnswerRequest,
    db: Session = Depends(get_db),
) -> ResearchQuestionAnswerResponse:
    _assert_v2_enabled()

    try:
        row = answer_research_question(db, question_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ResearchQuestionAnswerResponse(
        question=ResearchQuestionView(
            question_id=row.id,
            job_id=row.job_id,
            session_id=row.session_id,
            person_xref=row.person_xref,
            relationship=row.relationship,
            status=row.status,
            question=row.question,
            rationale=row.rationale,
            answer=row.answer,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    )


@sessions_router.post("/{session_id}/research/apply-approved", response_model=ApplyApprovedResponse)
def apply_approved_research_proposals(
    session_id: str,
    body: ApplyApprovedRequest,
    db: Session = Depends(get_db),
) -> ApplyApprovedResponse:
    _assert_v2_enabled()

    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = apply_approved_proposals(db, session_id, job_id=body.job_id)
    return ApplyApprovedResponse(applied_updates=result.applied_updates, skipped=result.skipped)


@sessions_router.post("/{session_id}/research/local-index", response_model=LocalFolderIndexResponse)
def build_local_folder_index(
    session_id: str,
    body: LocalFolderIndexRequest,
    db: Session = Depends(get_db),
) -> LocalFolderIndexResponse:
    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    configs = list_provider_configs(db)
    local_cfg = configs.get("local", {})
    folder_path = (body.folder_path or local_cfg.get("folder_path", "")).strip()
    if not folder_path:
        raise HTTPException(status_code=400, detail="Provide folder_path or set Provider Config > local.folder_path")

    try:
        index = index_local_folder(folder_path=folder_path, max_files=body.max_files)
    except LocalFolderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return LocalFolderIndexResponse(
        folder_path=index.folder_path,
        file_count=index.file_count,
        sample_files=index.sample_files,
    )


@sessions_router.post("/{session_id}/research/face-pair", response_model=FacePairResponse)
def run_face_pairing(
    session_id: str,
    body: FacePairRequest,
    db: Session = Depends(get_db),
) -> FacePairResponse:
    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    configs = list_provider_configs(db)
    local_cfg = configs.get("local", {})
    folder_path = (body.folder_path or local_cfg.get("folder_path", "")).strip()
    if not folder_path:
        raise HTTPException(status_code=400, detail="Provide folder_path or set Provider Config > local.folder_path")

    stmt: Select[tuple[Person]] = select(Person).where(Person.session_id == session_id).order_by(Person.id)
    people = [person for person in db.scalars(stmt).all() if not (person.is_living and not person.can_use_data)]

    try:
        report = pair_faces_to_people(
            folder_path=folder_path,
            people=people,
            max_images=body.max_images,
            threshold=body.threshold,
        )
    except FacePairingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FacePairResponse(
        engine=report.engine,
        scanned_images=report.scanned_images,
        reference_faces=report.reference_faces,
        skipped_images=report.skipped_images,
        pairs=[
            FacePairMatch(
                image_path=item.image_path,
                person_xref=item.person_xref,
                person_name=item.person_name,
                confidence=item.confidence,
                distance=item.distance,
            )
            for item in report.pairs
        ],
    )


router.include_router(sessions_router)
router.include_router(jobs_router)
