"""drop tournament scoring_rule

Revision ID: d7b2f4c19e83
Revises: a91d4c6b3e07
Create Date: 2026-09-05 14:00:00.000000

`best`-score mode is retired: a round counts each player's FIRST valid score,
full stop. The column only ever carried that choice, so it goes with the mode,
and the `scoring_rule` type with it -- d58b9d2d161a created the type for these
two columns and nothing else in the schema names it.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd7b2f4c19e83'
down_revision: Union[str, Sequence[str], None] = 'a91d4c6b3e07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


scoring_rule = postgresql.ENUM(
    'first', 'best', name='scoring_rule', create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('tournament_rounds', 'scoring_rule')
    op.drop_column('tournament_matches', 'scoring_rule')
    scoring_rule.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    scoring_rule.create(bind, checkfirst=True)
    # Every restored row reads `first`: it is the only rule that was ever
    # played, and the only one the code above this revision knows.
    for table in ('tournament_matches', 'tournament_rounds'):
        op.add_column(
            table,
            sa.Column(
                'scoring_rule',
                scoring_rule,
                server_default='first',
                nullable=False,
            ),
        )
