from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from deepgen.db import get_db
from deepgen.models import Person, UploadSession
from deepgen.schemas import ApplyProposalRequest, ResearchRequest, ResearchResponse
from deepgen.services.connectors import build_connectors
from deepgen.services.llm import LLMConfig, build_llm_client
from deepgen.services.provider_config import list_provider_configs
from deepgen.services.research import run_research

router = APIRouter(prefix="/api/sessions", tags=["research"])


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


@router.post("/{session_id}/research/run", response_model=ResearchResponse)
def run_session_research(
    session_id: str,
    body: ResearchRequest,
    db: Session = Depends(get_db),
) -> ResearchResponse:
    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    configs = list_provider_configs(db)
    llm_cfg = configs.get("llm", {})
    openai_cfg = configs.get("openai", {})
    mlx_cfg = configs.get("mlx", {})

    llm_client = build_llm_client(
        LLMConfig(
            backend=llm_cfg.get("backend", "openai"),
            openai_api_key=openai_cfg.get("api_key", ""),
            openai_model=openai_cfg.get("model", "gpt-4.1-mini"),
            mlx_model=mlx_cfg.get("model", "mlx-community/Llama-3.2-3B-Instruct-4bit"),
        )
    )
    connectors = build_connectors(configs)
    findings = run_research(
        db=db,
        session_id=session_id,
        people_xrefs=body.person_xrefs,
        max_people=body.max_people,
        connectors=connectors,
        llm_client=llm_client,
    )
    return ResearchResponse(
        llm_backend=llm_cfg.get("backend", "openai"),
        source_connectors=[connector.name for connector in connectors],
        findings=findings,
    )


@router.post("/{session_id}/research/apply-proposals")
def apply_research_proposals(
    session_id: str,
    body: ApplyProposalRequest,
    db: Session = Depends(get_db),
):
    session = db.get(UploadSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    applied = 0
    for update in body.updates:
        stmt: Select[tuple[Person]] = select(Person).where(
            Person.session_id == session_id, Person.xref == update.child_xref
        )
        child = db.scalars(stmt).first()
        if not child:
            continue

        if update.father_name and not child.father_xref:
            xref = _next_xref(db, session_id)
            father = Person(
                session_id=session_id,
                xref=xref,
                name=update.father_name,
                sex="M",
                is_living=False,
                can_use_data=True,
                can_llm_research=True,
            )
            db.add(father)
            db.flush()
            child.father_xref = father.xref
            applied += 1

        if update.mother_name and not child.mother_xref:
            xref = _next_xref(db, session_id)
            mother = Person(
                session_id=session_id,
                xref=xref,
                name=update.mother_name,
                sex="F",
                is_living=False,
                can_use_data=True,
                can_llm_research=True,
            )
            db.add(mother)
            db.flush()
            child.mother_xref = mother.xref
            applied += 1

    db.commit()
    return {"applied_updates": applied}
