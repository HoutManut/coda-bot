"""rename the b30 depth config key and its values to b50

Arcaea 7.0 replaced the best-30 pool with best-50, so ``recent_b30_stat`` and the
``b30``/``b40`` depth values both name a model that no longer exists.

Both halves are load-bearing, for different reasons. The KEY rename alone would
be silent preference loss -- ``resolve`` looks the key up by name and would fall
through to the default, leaving every opted-in user's row unread forever (the
same orphaning ``f1a2b3c4d5e6`` cleaned up). The VALUE rename is worse than that:
the read path never validates against the registry's option tuple, so a stale
``b30`` is returned verbatim and then raises ``KeyError`` off ``_MODE_REACH`` on
every ``/recent`` and ``/score`` that user runs.

``b40`` maps to ``b60`` -- the "just past the pool" reach, rescaled to the new
pool size -- so nobody's stored preference disappears. ``score_rank_depth`` keeps
its name but still holds the old values, so it is rewritten too.

Data-only, and irreversible by design: downgrade cannot tell a rewritten row from
one that always held that value.

Revision ID: a5e0c91d7f34
Revises: 1acd77155bd9
Create Date: 2026-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a5e0c91d7f34'
down_revision: Union[str, Sequence[str], None] = '1acd77155bd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEPTH_KEYS = ("recent_b50_stat", "score_rank_depth")
_VALUE_RENAMES = (("b30", "b50"), ("b40", "b60"))


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "UPDATE config_values SET key = 'recent_b50_stat' "
            "WHERE key = 'recent_b30_stat'"
        )
    )
    for old, new in _VALUE_RENAMES:
        op.execute(
            sa.text(
                "UPDATE config_values "
                "SET value = jsonb_set(value, '{v}', to_jsonb(:new ::text)) "
                "WHERE key = ANY(:keys) AND value->>'v' = :old"
            ).bindparams(new=new, keys=list(_DEPTH_KEYS), old=old)
        )


def downgrade() -> None:
    """Downgrade schema."""
    pass
