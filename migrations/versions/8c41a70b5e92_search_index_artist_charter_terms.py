"""search_index: union artist + charter aliases

Fills the ``entity_ref_id`` slot d3f9a1c07b2e left open ("artist/charter aliases
are deliberately not unioned in yet ... their rows slot in here when added"), so
``artist:`` / ``charter:`` filters can resolve a name to entity ids.

Packs are deliberately absent: ``songs.pack_name`` is denormalized onto the song
row, and pack renames never touch ``aliassync``, so a pack arm here would go
stale on every pack edit.

Revision ID: 8c41a70b5e92
Revises: 705ec00fbbd8
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c41a70b5e92'
down_revision: Union[str, Sequence[str], None] = '705ec00fbbd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SONG_AND_DIFFICULTY_ARMS = """
SELECT 'song'::text        AS entity_type,
       sa.song_id          AS song_id,
       NULL::integer       AS difficulty_id,
       NULL::difficulty_class AS difficulty_class,
       NULL::varchar       AS entity_ref_id,
       sa.alias            AS term
FROM song_aliases sa
UNION ALL
SELECT 'difficulty'::text  AS entity_type,
       sd.song_id          AS song_id,
       da.difficulty_id    AS difficulty_id,
       sd.difficulty       AS difficulty_class,
       NULL::varchar       AS entity_ref_id,
       da.alias            AS term
FROM difficulty_aliases da
JOIN song_difficulties sd ON sd.id = da.difficulty_id
"""

_ENTITY_ARMS = """
UNION ALL
SELECT 'artist'::text      AS entity_type,
       NULL::varchar       AS song_id,
       NULL::integer       AS difficulty_id,
       NULL::difficulty_class AS difficulty_class,
       aa.artist_id        AS entity_ref_id,
       aa.alias            AS term
FROM artist_aliases aa
UNION ALL
SELECT 'charter'::text     AS entity_type,
       NULL::varchar       AS song_id,
       NULL::integer       AS difficulty_id,
       NULL::difficulty_class AS difficulty_class,
       ca.charter_id       AS entity_ref_id,
       ca.alias            AS term
FROM charter_aliases ca
"""

_INDEXES = (
    "CREATE INDEX ix_search_index_term_trgm "
    "ON search_index USING gin (lower(term) gin_trgm_ops)",
    "CREATE INDEX ix_search_index_term_lower ON search_index (lower(term))",
)


def _rebuild(body: str) -> None:
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS search_index"))
    op.execute(sa.text(f"CREATE MATERIALIZED VIEW search_index AS {body}"))
    for statement in _INDEXES:
        op.execute(sa.text(statement))


def upgrade() -> None:
    """Upgrade schema."""
    _rebuild(_SONG_AND_DIFFICULTY_ARMS + _ENTITY_ARMS)


def downgrade() -> None:
    """Downgrade schema."""
    _rebuild(_SONG_AND_DIFFICULTY_ARMS)
