import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytest.importorskip("pydantic_settings")

from deepgen.db import Base
from deepgen.models import Person, UploadSession
from deepgen.routers.sessions_router import session_people


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


def test_session_people_exposes_parent_links(db_session: Session):
    db_session.add(UploadSession(id="sess1", filename="sample.ged", gedcom_version="5.5.1"))
    db_session.add(
        Person(
            session_id="sess1",
            xref="@I1@",
            name="John Doe",
            sex="M",
            is_living=False,
            can_use_data=True,
            can_llm_research=True,
        )
    )
    db_session.add(
        Person(
            session_id="sess1",
            xref="@I2@",
            name="Mary Smith",
            sex="F",
            is_living=False,
            can_use_data=True,
            can_llm_research=True,
        )
    )
    db_session.add(
        Person(
            session_id="sess1",
            xref="@I3@",
            name="Jane Doe",
            sex="F",
            birth_date="1 JAN 1930",
            birth_year=1930,
            father_xref="@I1@",
            mother_xref="@I2@",
            is_living=True,
            can_use_data=False,
            can_llm_research=False,
        )
    )
    db_session.commit()

    people = session_people("sess1", db=db_session)
    by_xref = {p.xref: p for p in people}
    assert by_xref["@I3@"].father_xref == "@I1@"
    assert by_xref["@I3@"].mother_xref == "@I2@"
    assert by_xref["@I3@"].birth_year == 1930

