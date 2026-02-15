from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytest.importorskip("pydantic_settings")

from deepgen.db import Base
from deepgen.models import UploadSession
from deepgen.services.document_index import (
    index_uploaded_document,
    list_indexed_documents,
    reindex_session_documents,
    search_indexed_documents,
)


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch) -> Session:
    monkeypatch.chdir(tmp_path)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_upload_indexes_and_dedupes_by_hash(db_session: Session):
    db_session.add(UploadSession(id="sess1", filename="tree.ged", gedcom_version="7.0"))
    db_session.commit()

    payload = b"John Doe born 1900 in Boston"
    first = index_uploaded_document(
        db_session,
        session_id="sess1",
        filename="john_notes.txt",
        content_bytes=payload,
        content_type="text/plain",
    )
    second = index_uploaded_document(
        db_session,
        session_id="sess1",
        filename="john_notes_copy.txt",
        content_bytes=payload,
        content_type="text/plain",
    )

    assert first.id == second.id

    rows, total = list_indexed_documents(db_session, session_id="sess1", limit=20, offset=0)
    assert total == 1
    assert rows[0].original_filename == "john_notes.txt"


def test_search_and_reindex(db_session: Session):
    db_session.add(UploadSession(id="sess2", filename="tree.ged", gedcom_version="7.0"))
    db_session.commit()

    row = index_uploaded_document(
        db_session,
        session_id="sess2",
        filename="mary_smith_notes.txt",
        content_bytes=b"Mary Smith likely appears in 1930 census.",
        content_type="text/plain",
    )

    hits = search_indexed_documents(db_session, session_id="sess2", query="mary census", limit=10)
    assert len(hits) == 1
    assert hits[0].id == row.id

    stats = reindex_session_documents(db_session, session_id="sess2")
    assert stats["total"] == 1
    assert stats["indexed"] == 1
    assert stats["skipped"] == 0
