"""add_access_decisions_table

Revision ID: af5c136a9d37
Revises: 001_initial
Create Date: 2025-12-11 01:12:08.151784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'af5c136a9d37'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create decision_status enum type
    decision_status_enum = postgresql.ENUM(
        'APPROVED', 'REJECTED', 'MANUAL_REVIEW', 'OVERRIDDEN',
        name='decision_status',
        create_type=True
    )
    decision_status_enum.create(op.get_bind(), checkfirst=True)

    # Create access_decisions table
    op.create_table('access_decisions',
        sa.Column('decision_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=100), nullable=False),
        sa.Column('gate_id', sa.Integer(), nullable=False),
        sa.Column('decision', postgresql.ENUM('APPROVED', 'REJECTED', 'MANUAL_REVIEW', 'OVERRIDDEN', name='decision_status', create_type=False), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('license_plate', sa.String(length=20), nullable=True),
        sa.Column('un_number', sa.String(length=10), nullable=True),
        sa.Column('kemler_code', sa.String(length=10), nullable=True),
        sa.Column('plate_image_url', sa.String(length=500), nullable=True),
        sa.Column('hazard_image_url', sa.String(length=500), nullable=True),
        sa.Column('route', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('alerts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('lp_confidence', sa.Float(), nullable=True),
        sa.Column('hz_confidence', sa.Float(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('original_decision', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['gate_id'], ['gates.gate_id'], ),
        sa.ForeignKeyConstraint(['reviewed_by'], ['workers.worker_id'], ),
        sa.PrimaryKeyConstraint('decision_id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_access_decisions_event_id'), 'access_decisions', ['event_id'], unique=True)
    op.create_index(op.f('ix_access_decisions_license_plate'), 'access_decisions', ['license_plate'], unique=False)
    op.create_index('ix_access_decisions_gate_created', 'access_decisions', ['gate_id', sa.text('created_at DESC')], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_access_decisions_gate_created', table_name='access_decisions')
    op.drop_index(op.f('ix_access_decisions_license_plate'), table_name='access_decisions')
    op.drop_index(op.f('ix_access_decisions_event_id'), table_name='access_decisions')
    
    # Drop table
    op.drop_table('access_decisions')
    
    # Drop enum type
    decision_status_enum = postgresql.ENUM(
        'APPROVED', 'REJECTED', 'MANUAL_REVIEW', 'OVERRIDDEN',
        name='decision_status'
    )
    decision_status_enum.drop(op.get_bind(), checkfirst=True)
