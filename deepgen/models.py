from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from deepgen.db import Base


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    gedcom_version: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    people: Mapped[list["Person"]] = relationship(
        "Person",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("session_id", "xref", name="uq_session_xref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("upload_sessions.id"), nullable=False)
    xref: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Unknown")
    sex: Mapped[str | None] = mapped_column(String(16))
    birth_date: Mapped[str | None] = mapped_column(String(64))
    death_date: Mapped[str | None] = mapped_column(String(64))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    is_living: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_use_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_llm_research: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    father_xref: Mapped[str | None] = mapped_column(String(64))
    mother_xref: Mapped[str | None] = mapped_column(String(64))

    session: Mapped["UploadSession"] = relationship("UploadSession", back_populates="people")


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("upload_sessions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    llm_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    prompt_template_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v2")
    target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parse_repair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage_stats_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("research_jobs.id"), nullable=False)
    person_xref: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    normalized_title_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    retrieval_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ExtractedClaim(Base):
    __tablename__ = "extracted_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("research_jobs.id"), nullable=False)
    person_xref: Mapped[str] = mapped_column(String(64), nullable=False)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_name: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contradiction_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    parse_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ParentProposal(Base):
    __tablename__ = "parent_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("research_jobs.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("upload_sessions.id"), nullable=False)
    person_xref: Mapped[str] = mapped_column(String(64), nullable=False)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_name: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contradiction_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    score_components_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ProposalDecision(Base):
    __tablename__ = "proposal_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(Integer, ForeignKey("parent_proposals.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(64), nullable=False, default="user")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ApplyAuditEvent(Base):
    __tablename__ = "apply_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("research_jobs.id"))
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("upload_sessions.id"), nullable=False)
    proposal_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("parent_proposals.id"))
    child_xref: Mapped[str] = mapped_column(String(64), nullable=False)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_person_xref: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
