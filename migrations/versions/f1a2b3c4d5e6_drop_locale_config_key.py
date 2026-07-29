"""drop the locale config key

Discord's ``interaction.locale`` already carries the invoking user's display
language, so the key duplicated it and only ever applied to the one render path
that has no interaction. Its rows are orphaned once the key leaves REGISTRY --
``resolve`` reads REGISTRY, so they would sit unread forever.

Data-only, and irreversible by design: downgrade cannot invent values it deleted.

Revision ID: f1a2b3c4d5e6
Revises: 8c41a70b5e92
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '8c41a70b5e92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("DELETE FROM config_values WHERE key = 'locale'"))


def downgrade() -> None:
    """Downgrade schema."""
    pass
