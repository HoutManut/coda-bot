"""live update filters and guild floor

Revision ID: 7ac31e9b0d54
Revises: fba7cd1057fe
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ac31e9b0d54'
down_revision: Union[str, Sequence[str], None] = 'fba7cd1057fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # post_pb defaults true, so every user already switched on gets the intended
    # first-enable default (personal bests only) without a backfill statement.
    op.add_column('live_update_prefs', sa.Column('post_all', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('live_update_prefs', sa.Column('post_pb', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('live_update_prefs', sa.Column('post_pm', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('live_update_prefs', sa.Column('post_fr', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('live_update_prefs', sa.Column('best_of', sa.SmallInteger(), nullable=True))
    op.add_column('live_update_prefs', sa.Column('min_grade', sa.SmallInteger(), nullable=True))
    op.add_column('live_update_prefs', sa.Column('min_level', sa.SmallInteger(), nullable=True))

    op.add_column('live_update_channels', sa.Column('min_level', sa.SmallInteger(), nullable=True))
    op.add_column('live_update_channels', sa.Column('min_grade', sa.SmallInteger(), nullable=True))

    # The column was created defaulting to true while live updates are opt-in
    # (players.live.DEFAULT_ENABLED is False). Harmless so far only because
    # _upsert always passes `enabled` explicitly; align it before the poster
    # starts acting on the value.
    op.alter_column('live_update_prefs', 'enabled', server_default='false')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('live_update_prefs', 'enabled', server_default='true')

    op.drop_column('live_update_channels', 'min_grade')
    op.drop_column('live_update_channels', 'min_level')

    op.drop_column('live_update_prefs', 'min_level')
    op.drop_column('live_update_prefs', 'min_grade')
    op.drop_column('live_update_prefs', 'best_of')
    op.drop_column('live_update_prefs', 'post_fr')
    op.drop_column('live_update_prefs', 'post_pm')
    op.drop_column('live_update_prefs', 'post_pb')
    op.drop_column('live_update_prefs', 'post_all')
