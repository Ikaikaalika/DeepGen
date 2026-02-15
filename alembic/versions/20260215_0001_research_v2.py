"""Add research v2 persistence tables.

Revision ID: 202602150001
Revises: 
Create Date: 2026-02-15 00:01:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202602150001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("llm_backend", sa.String(length=32), nullable=False),
        sa.Column("llm_model", sa.String(length=128), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=32), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("parse_repair_count", sa.Integer(), nullable=False),
        sa.Column("stage_stats_json", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["upload_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("person_xref", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("normalized_title_hash", sa.String(length=64), nullable=False),
        sa.Column("retrieval_rank", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_items_job_person", "evidence_items", ["job_id", "person_xref"])

    op.create_table(
        "extracted_claims",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("person_xref", sa.String(length=64), nullable=False),
        sa.Column("relationship", sa.String(length=32), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_ids_json", sa.Text(), nullable=False),
        sa.Column("contradiction_flags_json", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("parse_valid", sa.Boolean(), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extracted_claims_job_person", "extracted_claims", ["job_id", "person_xref"])

    op.create_table(
        "parent_proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("person_xref", sa.String(length=64), nullable=False),
        sa.Column("relationship", sa.String(length=32), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("evidence_ids_json", sa.Text(), nullable=False),
        sa.Column("contradiction_flags_json", sa.Text(), nullable=False),
        sa.Column("score_components_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["upload_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parent_proposals_job", "parent_proposals", ["job_id"])
    op.create_index("ix_parent_proposals_session_status", "parent_proposals", ["session_id", "status"])

    op.create_table(
        "proposal_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("decided_by", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["parent_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "apply_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=True),
        sa.Column("child_xref", sa.String(length=64), nullable=False),
        sa.Column("relationship", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_person_xref", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["parent_proposals.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["upload_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_apply_audit_events_session", "apply_audit_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_apply_audit_events_session", table_name="apply_audit_events")
    op.drop_table("apply_audit_events")

    op.drop_table("proposal_decisions")

    op.drop_index("ix_parent_proposals_session_status", table_name="parent_proposals")
    op.drop_index("ix_parent_proposals_job", table_name="parent_proposals")
    op.drop_table("parent_proposals")

    op.drop_index("ix_extracted_claims_job_person", table_name="extracted_claims")
    op.drop_table("extracted_claims")

    op.drop_index("ix_evidence_items_job_person", table_name="evidence_items")
    op.drop_table("evidence_items")

    op.drop_table("research_jobs")
