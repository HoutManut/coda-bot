"""artist/charter/pack fk on update cascade

Revision ID: b3f1c2d4e5a6
Revises: ee44bef1077a
Create Date: 2026-05-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b3f1c2d4e5a6'
down_revision: Union[str, Sequence[str], None] = 'ee44bef1077a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, fk column, parent table, parent column) for every FK that should follow
# a renamed artist/charter/pack PK — same treatment song_id got in 66ad9752c1d2.
_FKS = (
    ("artist_aliases", "artist_id", "artists", "artist_id"),
    ("song_artists", "artist_id", "artists", "artist_id"),
    ("difficulty_artists", "artist_id", "artists", "artist_id"),
    ("charter_aliases", "charter_id", "charters", "charter_id"),
    ("song_charters", "charter_id", "charters", "charter_id"),
    ("difficulty_charters", "charter_id", "charters", "charter_id"),
    ("songs", "pack_id", "packs", "pack_id"),
)


def upgrade() -> None:
    """Make the artist/charter/pack FKs cascade on a PK rename, so editing an
    entity's id repoints its links/aliases (and a pack's songs) automatically."""
    for table, col, parent, parent_col in _FKS:
        name = f"{table}_{col}_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, parent, [col], [parent_col], onupdate="CASCADE"
        )


def downgrade() -> None:
    """Restore the plain (no ON UPDATE) FKs."""
    for table, col, parent, parent_col in _FKS:
        name = f"{table}_{col}_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, parent, [col], [parent_col])
