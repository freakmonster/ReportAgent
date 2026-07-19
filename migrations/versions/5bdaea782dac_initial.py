"""initial

Revision ID: 5bdaea782dac
Revises: 
Create Date: 2026-07-17 18:23:19.099457

Creates workfow_states, index_status tables, and the update_workflow_timestamp trigger.
workflow_info table is managed separately (created via init_db.py raw DDL).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5bdaea782dac'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── Tables ──────────────────────────────────────────────────────────
    op.create_table('index_status',
    sa.Column('collection_name', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('error_msg', sa.Text(), nullable=True),
    sa.Column('checksum', sa.Text(), nullable=True),
    sa.Column('document_count', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('collection_name')
    )
    op.create_table('workflow_states',
    sa.Column('workflow_id', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('state_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('user_id', sa.Text(), nullable=False),
    sa.Column('template_name', sa.Text(), nullable=False),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('workflow_id')
    )

    # ── Trigger: auto-update updated_at on workflow_info ───────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_workflow_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_workflow_updated ON workflow_info")
    op.execute("""
        CREATE TRIGGER trg_workflow_updated
            BEFORE UPDATE ON workflow_info
            FOR EACH ROW EXECUTE FUNCTION update_workflow_timestamp()
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_workflow_updated ON workflow_info")
    op.execute("DROP FUNCTION IF EXISTS update_workflow_timestamp")
    op.drop_table('workflow_states')
    op.drop_table('index_status')
