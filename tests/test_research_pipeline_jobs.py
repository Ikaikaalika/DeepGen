import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytest.importorskip("pydantic_settings")

from deepgen.db import Base
from deepgen.models import ParentProposal, Person, UploadSession
from deepgen.schemas import ProposalDecisionRequest, ResearchQuestionAnswerRequest
from deepgen.services.research_pipeline.backend_adapters import LLMRuntime
from deepgen.services.research_pipeline.jobs import (
    answer_research_question,
    create_research_job,
    decide_proposal,
    list_job_findings,
    list_job_proposals,
    list_job_questions,
    run_research_job,
)
from deepgen.services.source_types import SourceResult


class _FakeConnector:
    name = "fake"

    def search_person(self, name: str, birth_year: int | None):  # noqa: ARG002
        return [
            SourceResult(
                source="fake",
                title="Fake Census Record",
                url="https://example.com/records/1",
                note="seeded",
            )
        ]


class _BadConnector:
    name = "bad"

    def search_person(self, name: str, birth_year: int | None):  # noqa: ARG002
        raise RuntimeError("connector unavailable")


class _StubLLM:
    def generate(self, prompt: str) -> str:  # noqa: ARG002
        return (
            '{"claims":[{"relationship":"father","candidate_name":"John Doe","confidence":0.8,'
            '"rationale":"Likely father from record","evidence_ids":[1]}]}'
        )


class _NoClaimLLM:
    def generate(self, prompt: str) -> str:  # noqa: ARG002
        return '{"claims":[]}'


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


def _seed_session(db_session: Session):
    db_session.add(UploadSession(id="sess1", filename="sample.ged", gedcom_version="7.0"))
    db_session.add(
        Person(
            session_id="sess1",
            xref="@I10@",
            name="Jane Doe",
            sex="F",
            birth_year=1930,
            is_living=False,
            can_use_data=True,
            can_llm_research=True,
        )
    )
    db_session.commit()


def test_research_job_end_to_end(monkeypatch, db_session: Session):
    _seed_session(db_session)

    monkeypatch.setattr("deepgen.services.research_pipeline.jobs.list_provider_configs", lambda db: {})
    monkeypatch.setattr("deepgen.services.research_pipeline.jobs.build_connectors", lambda cfg: [_FakeConnector()])
    monkeypatch.setattr(
        "deepgen.services.research_pipeline.jobs.resolve_runtime",
        lambda cfg: LLMRuntime(backend="openai", model="stub", client=_StubLLM()),
    )

    job = create_research_job(
        db_session,
        session_id="sess1",
        people_xrefs=None,
        max_people=10,
        connector_overrides=None,
        prompt_template_version="v2",
    )
    run = run_research_job(db_session, job.id)

    assert run.status == "completed"
    assert run.completed_count == 1

    findings = list_job_findings(db_session, job.id)
    assert len(findings) == 1
    assert findings[0]["evidence_ids"]

    proposals, total = list_job_proposals(db_session, job.id, limit=20, offset=0)
    assert total == 2
    father = [p for p in proposals if p["relationship"] == "father"][0]
    assert father["candidate_name"] == "John Doe"
    assert father["evidence_ids"]


def test_research_job_isolation_when_one_connector_fails(monkeypatch, db_session: Session):
    _seed_session(db_session)

    monkeypatch.setattr("deepgen.services.research_pipeline.jobs.list_provider_configs", lambda db: {})
    monkeypatch.setattr(
        "deepgen.services.research_pipeline.jobs.build_connectors",
        lambda cfg: [_BadConnector(), _FakeConnector()],
    )
    monkeypatch.setattr(
        "deepgen.services.research_pipeline.jobs.resolve_runtime",
        lambda cfg: LLMRuntime(backend="anthropic", model="stub", client=_StubLLM()),
    )

    job = create_research_job(
        db_session,
        session_id="sess1",
        people_xrefs=None,
        max_people=10,
        connector_overrides=None,
        prompt_template_version="v2",
    )
    run = run_research_job(db_session, job.id)

    assert run.status == "completed"
    assert run.error_count >= 1


def test_proposal_decision_rejects_approval_without_citations(db_session: Session):
    _seed_session(db_session)

    db_session.add(
        ParentProposal(
            job_id="jobX",
            session_id="sess1",
            person_xref="@I10@",
            relationship="father",
            candidate_name="No Citation",
            confidence=0.4,
            status="pending_review",
            notes="",
            evidence_ids_json="[]",
            contradiction_flags_json="[]",
            score_components_json=json.dumps({"final_score": 0.4}),
        )
    )
    db_session.commit()

    proposal = db_session.query(ParentProposal).first()
    with pytest.raises(ValueError):
        decide_proposal(
            db_session,
            proposal.id,
            ProposalDecisionRequest(action="approve"),
        )


def test_list_job_proposals_pagination_and_order(db_session: Session):
    _seed_session(db_session)

    db_session.add_all(
        [
            ParentProposal(
                job_id="jobA",
                session_id="sess1",
                person_xref="@I20@",
                relationship="mother",
                candidate_name="A",
                confidence=0.1,
                status="pending_review",
                notes="",
                evidence_ids_json="[]",
                contradiction_flags_json="[]",
                score_components_json="{}",
            ),
            ParentProposal(
                job_id="jobA",
                session_id="sess1",
                person_xref="@I10@",
                relationship="father",
                candidate_name="B",
                confidence=0.2,
                status="pending_review",
                notes="",
                evidence_ids_json="[]",
                contradiction_flags_json="[]",
                score_components_json="{}",
            ),
            ParentProposal(
                job_id="jobA",
                session_id="sess1",
                person_xref="@I10@",
                relationship="mother",
                candidate_name="C",
                confidence=0.3,
                status="pending_review",
                notes="",
                evidence_ids_json="[]",
                contradiction_flags_json="[]",
                score_components_json="{}",
            ),
        ]
    )
    db_session.commit()

    first_page, total = list_job_proposals(db_session, "jobA", limit=2, offset=0)
    second_page, _ = list_job_proposals(db_session, "jobA", limit=2, offset=2)

    assert total == 3
    assert [item["relationship"] for item in first_page] == ["father", "mother"]
    assert [item["person_xref"] for item in second_page] == ["@I20@"]


def test_agentic_questions_created_and_answer_reused(monkeypatch, db_session: Session):
    _seed_session(db_session)

    monkeypatch.setattr("deepgen.services.research_pipeline.jobs.list_provider_configs", lambda db: {})
    monkeypatch.setattr("deepgen.services.research_pipeline.jobs.build_connectors", lambda cfg: [])
    monkeypatch.setattr(
        "deepgen.services.research_pipeline.jobs.resolve_runtime",
        lambda cfg: LLMRuntime(backend="openai", model="stub", client=_NoClaimLLM()),
    )

    first_job = create_research_job(
        db_session,
        session_id="sess1",
        people_xrefs=None,
        max_people=10,
        connector_overrides=None,
        prompt_template_version="v2",
    )
    run_research_job(db_session, first_job.id)

    questions, total = list_job_questions(db_session, first_job.id)
    assert total > 0
    pending = [q for q in questions if q["status"] == "pending"]
    assert pending

    question_id = pending[0]["question_id"]
    answer_research_question(
        db_session,
        question_id,
        body=ResearchQuestionAnswerRequest(status="answered", answer="Her father might be John Patrick Doe"),
    )

    second_job = create_research_job(
        db_session,
        session_id="sess1",
        people_xrefs=None,
        max_people=10,
        connector_overrides=None,
        prompt_template_version="v2",
    )
    run_research_job(db_session, second_job.id)

    findings = list_job_findings(db_session, second_job.id)
    assert findings
    sources = [item["source"] for item in findings[0]["evidence"]]
    assert "user_answers" in sources
