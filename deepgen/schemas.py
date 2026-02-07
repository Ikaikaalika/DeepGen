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


class ResearchRequest(BaseModel):
    person_xrefs: list[str] | None = None
    max_people: int = 10


class PersonProposal(BaseModel):
    name: str
    relationship: str
    confidence: float
    notes: str


class ResearchFinding(BaseModel):
    person_xref: str
    person_name: str
    summary: str
    proposals: list[PersonProposal]


class ResearchResponse(BaseModel):
    llm_backend: str
    source_connectors: list[str]
    findings: list[ResearchFinding]


class ApplyProposalItem(BaseModel):
    child_xref: str
    father_name: str | None = None
    mother_name: str | None = None


class ApplyProposalRequest(BaseModel):
    updates: list[ApplyProposalItem] = Field(default_factory=list)
