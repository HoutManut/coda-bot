"""tournament matches rounds pool

Revision ID: d58b9d2d161a
Revises: a5e0c91d7f34
Create Date: 2026-09-02 12:43:53.902056

``thread_visibility`` and ``scoring_rule`` are each used by two tables, so the
enum types are created once up front and every column carries
``create_type=False``: left to ``create_table``, the second table's CREATE TYPE
fails on a type that already exists. ``difficulty_class`` predates this
revision and is only referenced, never created or dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd58b9d2d161a'
down_revision: Union[str, Sequence[str], None] = 'a5e0c91d7f34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


thread_visibility = postgresql.ENUM(
    'public', 'private', name='thread_visibility', create_type=False)
match_state = postgresql.ENUM(
    'scheduled', 'draft', 'pickban', 'playing', 'closed', 'cancelled',
    name='match_state', create_type=False)
pool_entry_state = postgresql.ENUM(
    'available', 'banned', 'picked', name='pool_entry_state', create_type=False)
round_state = postgresql.ENUM(
    'pending', 'open', 'grace', 'closed', 'cancelled',
    name='round_state', create_type=False)
scoring_rule = postgresql.ENUM(
    'first', 'best', name='scoring_rule', create_type=False)
difficulty_class = postgresql.ENUM(
    'pst', 'prs', 'ftr', 'byd', 'etr', 'byd_2', 'err',
    name='difficulty_class', create_type=False)

NEW_ENUMS = (
    thread_visibility, match_state, pool_entry_state, round_state, scoring_rule)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    for enum in NEW_ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table('tournament_channels',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('channel_id', sa.BigInteger(), nullable=False),
    sa.Column('set_by', sa.BigInteger(), nullable=False),
    sa.Column('set_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('guild_id')
    )
    op.create_table('tournament_matches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('home_channel_id', sa.BigInteger(), nullable=False),
    sa.Column('thread_id', sa.BigInteger(), nullable=False),
    sa.Column('board_message_id', sa.BigInteger(), nullable=True),
    sa.Column('visibility', thread_visibility, nullable=False),
    sa.Column('tournament_id', sa.Integer(), nullable=True),
    sa.Column('stage_label', sa.String(length=32), nullable=True),
    sa.Column('pick_ban', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('best_of', sa.SmallInteger(), nullable=False),
    sa.Column('scoring_rule', scoring_rule, server_default='first', nullable=False),
    sa.Column('difficulty_class', difficulty_class, nullable=True),
    sa.Column('level_min', sa.SmallInteger(), nullable=True),
    sa.Column('level_max', sa.SmallInteger(), nullable=True),
    sa.Column('state', match_state, server_default='draft', nullable=False),
    sa.Column('play_by_ms', sa.BigInteger(), nullable=True),
    sa.Column('turn_index', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('turn_deadline_ms', sa.BigInteger(), nullable=True),
    sa.Column('creator_discord_id', sa.BigInteger(), nullable=False),
    sa.Column('admin_gated', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tournament_matches_turn', 'tournament_matches', ['state', 'turn_deadline_ms'], unique=False)
    op.create_table('tournament_threads',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('roster_key', sa.ARRAY(sa.Integer()), nullable=False),
    sa.Column('visibility', thread_visibility, nullable=False),
    sa.Column('thread_id', sa.BigInteger(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('guild_id', 'roster_key', 'visibility', name='uq_tournament_threads_key')
    )
    op.create_table('tournament_rounds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('ordinal', sa.SmallInteger(), nullable=False),
    sa.Column('state', round_state, server_default='pending', nullable=False),
    sa.Column('scoring_rule', scoring_rule, server_default='first', nullable=False),
    sa.Column('start_ms', sa.BigInteger(), nullable=True),
    sa.Column('end_ms', sa.BigInteger(), nullable=True),
    sa.Column('grace_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['match_id'], ['tournament_matches.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('match_id', 'ordinal', name='uq_tournament_rounds_ordinal')
    )
    op.create_index('ix_tournament_rounds_deadline', 'tournament_rounds', ['state', 'end_ms'], unique=False)
    op.create_table('tournament_participants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('arcaea_account_id', sa.Integer(), nullable=False),
    sa.Column('side_index', sa.SmallInteger(), nullable=False),
    sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['arcaea_account_id'], ['arcaea_accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['match_id'], ['tournament_matches.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('match_id', 'arcaea_account_id', name='uq_tournament_participants_account')
    )
    op.create_table('tournament_charts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('round_id', sa.Integer(), nullable=False),
    sa.Column('song_difficulty_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['round_id'], ['tournament_rounds.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['song_difficulty_id'], ['song_difficulties.id'], onupdate='CASCADE', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('round_id', 'song_difficulty_id', name='uq_tournament_charts_chart')
    )
    op.create_table('tournament_pool_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('song_id', sa.String(), nullable=False),
    sa.Column('song_difficulty_id', sa.Integer(), nullable=True),
    sa.Column('ordinal', sa.SmallInteger(), nullable=False),
    sa.Column('state', pool_entry_state, server_default='available', nullable=False),
    sa.Column('acted_by', sa.Integer(), nullable=True),
    sa.Column('acted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('auto', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('round_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['acted_by'], ['arcaea_accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['match_id'], ['tournament_matches.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['round_id'], ['tournament_rounds.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['song_difficulty_id'], ['song_difficulties.id'], onupdate='CASCADE', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['song_id'], ['songs.song_id'], onupdate='CASCADE', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('match_id', 'ordinal', name='uq_tournament_pool_ordinal'),
    sa.UniqueConstraint('match_id', 'song_id', name='uq_tournament_pool_song')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tournament_pool_entries')
    op.drop_table('tournament_charts')
    op.drop_table('tournament_participants')
    op.drop_index('ix_tournament_rounds_deadline', table_name='tournament_rounds')
    op.drop_table('tournament_rounds')
    op.drop_table('tournament_threads')
    op.drop_index('ix_tournament_matches_turn', table_name='tournament_matches')
    op.drop_table('tournament_matches')
    op.drop_table('tournament_channels')
    # drop_table does not drop the enum types create_type/create() made.
    bind = op.get_bind()
    for enum in NEW_ENUMS:
        enum.drop(bind, checkfirst=True)
