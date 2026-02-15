"""Add research question loop table.

Revision ID: 202602150003
Revises: 202602150002
Create Date: 2026-02-15 00:03:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202602150003"
down_revision = "202602150002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("person_xref", sa.String(length=64), nullable=False),
        sa.Column("relationship", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["upload_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_questions_job", "research_questions", ["job_id"])
    op.create_index("ix_research_questions_session_person", "research_questions", ["session_id", "person_xref"])


def downgrade() -> None:
    op.drop_index("ix_research_questions_session_person", table_name="research_questions")
    op.drop_index("ix_research_questions_job", table_name="research_questions")
    op.drop_table("research_questions")
