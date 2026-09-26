"""tournament match prompt key and message

Revision ID: f7c2b91e0a34
Revises: c3f19a0d47b2
Create Date: 2026-09-04 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c2b91e0a34'
down_revision: Union[str, Sequence[str], None] = 'c3f19a0d47b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'tournament_matches', sa.Column('prompt_key', sa.String(length=32), nullable=True)
    )
    op.add_column(
        'tournament_matches', sa.Column('prompt_message_id', sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tournament_matches', 'prompt_message_id')
    op.drop_column('tournament_matches', 'prompt_key')
