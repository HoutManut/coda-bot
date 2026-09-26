"""tournament round closed_ms

Revision ID: c3f19a0d47b2
Revises: e481b588edab
Create Date: 2026-09-04 21:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f19a0d47b2'
down_revision: Union[str, Sequence[str], None] = 'e481b588edab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'tournament_rounds', sa.Column('closed_ms', sa.BigInteger(), nullable=True)
    )
    # Rounds decided before this column existed spent their full backstop, so
    # backfilling it with that value is exact rather than an approximation.
    op.execute(
        "UPDATE tournament_rounds SET closed_ms = end_ms + grace_ms "
        "WHERE state = 'closed' AND end_ms IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tournament_rounds', 'closed_ms')
