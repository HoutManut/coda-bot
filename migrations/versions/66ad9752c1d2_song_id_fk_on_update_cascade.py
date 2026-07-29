"""song_id fk on update cascade

Revision ID: 66ad9752c1d2
Revises: efbbe73d0c06
Create Date: 2026-05-24 11:53:45.247018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66ad9752c1d2'
down_revision: Union[str, Sequence[str], None] = 'efbbe73d0c06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Child tables whose song_id FK should follow a renamed songs.song_id PK.
_CHILDREN = ("song_aliases", "song_artists", "song_charters", "song_difficulties")


def upgrade() -> None:
    """Make the song_id FKs cascade on a PK rename, so editing a song's id
    repoints its difficulties/links/aliases automatically."""
    for table in _CHILDREN:
        name = f"{table}_song_id_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, "songs", ["song_id"], ["song_id"], onupdate="CASCADE"
        )


def downgrade() -> None:
    """Restore the plain (no ON UPDATE) FKs."""
    for table in _CHILDREN:
        name = f"{table}_song_id_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "songs", ["song_id"], ["song_id"])
