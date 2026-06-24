"""Add missing metadata fields

Revision ID: a1b2c3d4e5f6
Revises: 0d2ee2341b80
Create Date: 2026-06-24 08:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0d2ee2341b80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dataset_metadata', sa.Column('annotator_qualifications', sa.String(length=50), nullable=True))
    op.add_column('dataset_metadata', sa.Column('dq_checks_applied', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('dataset_metadata', sa.Column('direct_identifiers_present', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('dataset_metadata', sa.Column('k_anonymity_value', sa.Integer(), nullable=True))
    op.add_column('dataset_metadata', sa.Column('location_granularity', sa.String(length=50), nullable=True))
    op.add_column('dataset_metadata', sa.Column('temporal_granularity', sa.String(length=50), nullable=True))
    op.add_column('dataset_metadata', sa.Column('rare_condition_flag', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('dataset_metadata', sa.Column('synthetic_utility_evaluated', sa.Boolean(), nullable=True))
    op.add_column('dataset_metadata', sa.Column('synthetic_privacy_tested', sa.Boolean(), nullable=True))
    op.add_column('dataset_metadata', sa.Column('equity_analysis_performed', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('dataset_metadata', sa.Column('community_engagement', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('dataset_metadata', sa.Column('redressal_mechanism_exists', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('dataset_metadata', sa.Column('dua_required', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('dataset_metadata', sa.Column('named_steward_exists', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('dataset_metadata', sa.Column('dpdp_compliance_status', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('dataset_metadata', 'dpdp_compliance_status')
    op.drop_column('dataset_metadata', 'named_steward_exists')
    op.drop_column('dataset_metadata', 'dua_required')
    op.drop_column('dataset_metadata', 'redressal_mechanism_exists')
    op.drop_column('dataset_metadata', 'community_engagement')
    op.drop_column('dataset_metadata', 'equity_analysis_performed')
    op.drop_column('dataset_metadata', 'synthetic_privacy_tested')
    op.drop_column('dataset_metadata', 'synthetic_utility_evaluated')
    op.drop_column('dataset_metadata', 'rare_condition_flag')
    op.drop_column('dataset_metadata', 'temporal_granularity')
    op.drop_column('dataset_metadata', 'location_granularity')
    op.drop_column('dataset_metadata', 'k_anonymity_value')
    op.drop_column('dataset_metadata', 'direct_identifiers_present')
    op.drop_column('dataset_metadata', 'dq_checks_applied')
    op.drop_column('dataset_metadata', 'annotator_qualifications')
