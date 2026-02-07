from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
