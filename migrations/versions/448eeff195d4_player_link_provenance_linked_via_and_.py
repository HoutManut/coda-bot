"""player_link provenance: linked_via and is_owner

Revision ID: 448eeff195d4
Revises: 72cf0122181a
Create Date: 2026-07-18 01:41:01.125503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '448eeff195d4'
down_revision: Union[str, Sequence[str], None] = '72cf0122181a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # add_column does not auto-create the enum type (unlike create_table); do it
    # explicitly, matching 9a4cb65d96c8's artist_kind pattern.
    link_method = sa.Enum('code', 'account', name='link_method')
    link_method.create(op.get_bind(), checkfirst=True)

    op.add_column('player_links', sa.Column('linked_via', link_method, server_default='code', nullable=False))
    op.add_column('player_links', sa.Column('is_owner', sa.Boolean(), server_default='false', nullable=False))

    # Backfill: the oldest link per account (by linked_at, then id) is its owner.
    # Runs before the partial unique index so it never sees two owners at once.
    op.execute(
        sa.text(
            """
            UPDATE player_links pl SET is_owner = true
            WHERE pl.id = (
                SELECT p2.id FROM player_links p2
                WHERE p2.arcaea_account_id = pl.arcaea_account_id
                ORDER BY p2.linked_at ASC, p2.id ASC
                LIMIT 1
            )
            """
        )
    )

    # At most one owner per account, DB-enforced.
    op.create_index('uq_player_links_owner', 'player_links', ['arcaea_account_id'], unique=True, postgresql_where=sa.text('is_owner'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_player_links_owner', table_name='player_links', postgresql_where=sa.text('is_owner'))
    op.drop_column('player_links', 'is_owner')
    op.drop_column('player_links', 'linked_via')
    sa.Enum(name='link_method').drop(op.get_bind(), checkfirst=True)
