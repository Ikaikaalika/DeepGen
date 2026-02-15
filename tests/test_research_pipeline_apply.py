import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

pytest.importorskip("pydantic_settings")

from deepgen.db import Base
from deepgen.models import ApplyAuditEvent, ParentProposal, Person, ResearchJob, UploadSession
from deepgen.services.research_pipeline.apply import apply_approved_proposals


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_apply_approved_proposals_dedupes_parent_creation(db_session: Session):
    db_session.add(UploadSession(id="sess1", filename="sample.ged", gedcom_version="7.0"))
    db_session.add(
        ResearchJob(
            id="job1",
            session_id="sess1",
            status="completed",
            stage="completed",
            llm_backend="openai",
            llm_model="fake",
            prompt_template_version="v2",
            target_count=2,
            completed_count=2,
            error_count=0,
            progress=100.0,
            retry_count=0,
            parse_repair_count=0,
            stage_stats_json="{}",
        )
    )
    db_session.add_all(
        [
            Person(
                session_id="sess1",
                xref="@I1@",
                name="Child One",
                sex="F",
                is_living=False,
                can_use_data=True,
                can_llm_research=True,
            ),
            Person(
                session_id="sess1",
                xref="@I2@",
                name="Child Two",
                sex="F",
                is_living=False,
                can_use_data=True,
                can_llm_research=True,
            ),
        ]
    )
    db_session.add_all(
        [
            ParentProposal(
                job_id="job1",
                session_id="sess1",
                person_xref="@I1@",
                relationship="father",
                candidate_name="John Doe",
                confidence=0.8,
                status="approved",
                notes="approved",
                evidence_ids_json=json.dumps([11]),
                contradiction_flags_json="[]",
                score_components_json="{}",
            ),
            ParentProposal(
                job_id="job1",
                session_id="sess1",
                person_xref="@I2@",
                relationship="father",
                candidate_name="John Doe",
                confidence=0.78,
                status="approved",
                notes="approved",
                evidence_ids_json=json.dumps([12]),
                contradiction_flags_json="[]",
                score_components_json="{}",
            ),
        ]
    )
    db_session.commit()

    result = apply_approved_proposals(db_session, "sess1", job_id="job1")

    assert result.applied_updates == 2

    people = db_session.scalars(select(Person).where(Person.session_id == "sess1")).all()
    fathers = [p for p in people if p.sex == "M"]
    assert len(fathers) == 1

    child_one = db_session.scalars(select(Person).where(Person.session_id == "sess1", Person.xref == "@I1@")).one()
    child_two = db_session.scalars(select(Person).where(Person.session_id == "sess1", Person.xref == "@I2@")).one()

    assert child_one.father_xref == fathers[0].xref
    assert child_two.father_xref == fathers[0].xref

    audits = db_session.scalars(select(ApplyAuditEvent).where(ApplyAuditEvent.session_id == "sess1")).all()
    assert len(audits) == 2
