"""Add indexed user documents table.

Revision ID: 202602150002
Revises: 202602150001
Create Date: 2026-02-15 00:02:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202602150002"
down_revision = "202602150001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "indexed_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=2048), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("text_snippet", sa.Text(), nullable=False),
        sa.Column("indexed_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["upload_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "content_hash", name="uq_session_doc_hash"),
    )
    op.create_index("ix_indexed_documents_session", "indexed_documents", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_indexed_documents_session", table_name="indexed_documents")
    op.drop_table("indexed_documents")
