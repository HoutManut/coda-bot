"""tournament match open-join flag

Revision ID: a91d4c6b3e07
Revises: f7c2b91e0a34
Create Date: 2026-09-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a91d4c6b3e07'
down_revision: Union[str, Sequence[str], None] = 'f7c2b91e0a34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'tournament_matches',
        sa.Column(
            'open_join',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tournament_matches', 'open_join')
