from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProviderConfigUpdate(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class ProviderConfigView(BaseModel):
    provider: str
    values: dict[str, str]


class UploadSummary(BaseModel):
    session_id: str
    filename: str
    gedcom_version: str
    person_count: int
    living_count: int
    living_pending_count: int


class LivingPersonView(BaseModel):
    id: int
    xref: str
    name: str
    birth_date: str | None
    can_use_data: bool
    can_llm_research: bool


class PersonView(BaseModel):
    id: int
    xref: str
    name: str
    sex: str | None = None
    birth_date: str | None = None
    death_date: str | None = None
    birth_year: int | None = None
    is_living: bool
    can_use_data: bool
    can_llm_research: bool
    father_xref: str | None = None
    mother_xref: str | None = None


class IndexedDocumentView(BaseModel):
    id: int
    original_filename: str
    stored_path: str
    mime_type: str
    size_bytes: int
    source: str
    text_snippet: str
    created_at: datetime
    indexed_at: datetime


class DocumentUploadResponse(BaseModel):
    document: IndexedDocumentView


class DocumentListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    documents: list[IndexedDocumentView] = Field(default_factory=list)


class DocumentSearchResponse(BaseModel):
    query: str
    total: int
    documents: list[IndexedDocumentView] = Field(default_factory=list)


class DocumentReindexResponse(BaseModel):
    total: int
    indexed: int
    skipped: int


class PersonConsentUpdate(BaseModel):
    person_id: int
    can_use_data: bool
    can_llm_research: bool


class MarkAllConsent(BaseModel):
    can_use_data: bool
    can_llm_research: bool


class LivingConsentRequest(BaseModel):
    updates: list[PersonConsentUpdate] = Field(default_factory=list)
    mark_all: MarkAllConsent | None = None


class GapCandidate(BaseModel):
    person_id: int
    xref: str
    name: str
    missing_father: bool
    missing_mother: bool


class ResearchJobCreateRequest(BaseModel):
    person_xrefs: list[str] | None = None
    max_people: int = 10
    connector_overrides: dict[str, bool] | None = None


class ResearchJobCreateResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime


class ResearchJobStatusResponse(BaseModel):
    job_id: str
    session_id: str
    status: str
    stage: str
    progress: float
    target_count: int
    completed_count: int
    error_count: int
    retry_count: int
    parse_repair_count: int
    prompt_template_version: str
    llm_backend: str
    llm_model: str
    stage_durations_ms: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ResearchFindingEvidence(BaseModel):
    id: int
    source: str
    title: str
    url: str
    note: str


class ResearchFindingView(BaseModel):
    person_xref: str
    person_name: str
    summary: str
    evidence_ids: list[int] = Field(default_factory=list)
    evidence: list[ResearchFindingEvidence] = Field(default_factory=list)
    contradiction_flags: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, dict] = Field(default_factory=dict)
    proposal_ids: list[int] = Field(default_factory=list)


class ResearchFindingsResponse(BaseModel):
    job_id: str
    findings: list[ResearchFindingView] = Field(default_factory=list)


class ResearchProposalView(BaseModel):
    proposal_id: int
    job_id: str
    session_id: str
    person_xref: str
    relationship: str
    candidate_name: str | None = None
    confidence: float
    status: str
    notes: str
    evidence_ids: list[int] = Field(default_factory=list)
    contradiction_flags: list[str] = Field(default_factory=list)
    score_components: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ResearchProposalsResponse(BaseModel):
    job_id: str
    total: int
    limit: int
    offset: int
    proposals: list[ResearchProposalView] = Field(default_factory=list)


class ProposalDecisionRequest(BaseModel):
    action: Literal["approve", "reject", "edit"]
    candidate_name: str | None = None
    confidence: float | None = None
    notes: str | None = None


class ProposalDecisionResponse(BaseModel):
    proposal: ResearchProposalView


class ApplyApprovedRequest(BaseModel):
    job_id: str | None = None


class ApplyApprovedResponse(BaseModel):
    applied_updates: int
    skipped: list[dict[str, str]] = Field(default_factory=list)


class LocalFolderIndexRequest(BaseModel):
    folder_path: str | None = None
    max_files: int = 2000


class LocalFolderIndexResponse(BaseModel):
    folder_path: str
    file_count: int
    sample_files: list[str] = Field(default_factory=list)


class FacePairRequest(BaseModel):
    folder_path: str | None = None
    max_images: int = 400
    threshold: float = 0.52


class FacePairMatch(BaseModel):
    image_path: str
    person_xref: str
    person_name: str
    confidence: float
    distance: float


class FacePairResponse(BaseModel):
    engine: str
    scanned_images: int
    reference_faces: int
    skipped_images: int
    pairs: list[FacePairMatch] = Field(default_factory=list)
