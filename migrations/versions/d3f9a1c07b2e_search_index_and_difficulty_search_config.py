"""search_index matview + difficulty_search_config + pg_trgm

Revision ID: d3f9a1c07b2e
Revises: 460bea66bb35
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3f9a1c07b2e'
down_revision: Union[str, Sequence[str], None] = '460bea66bb35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# artist/charter aliases are deliberately not unioned in yet: v1 search resolves
# songs and charts only (handoff 09 §18). Their rows slot in here when added.
_SEARCH_INDEX_SQL = """
CREATE MATERIALIZED VIEW search_index AS
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

# Placeholder thresholds -- tunable in-DB without a deploy. err is hidden from
# broad search and only reachable via an explicit af-suffix intent.
_SEED_CONFIG_SQL = """
INSERT INTO difficulty_search_config
    (difficulty, hidden_from_broad, min_similarity, strong, af_suffixes)
VALUES
    ('pst',   false, 0.4, 0.55, NULL),
    ('prs',   false, 0.4, 0.55, NULL),
    ('ftr',   false, 0.4, 0.55, NULL),
    ('byd',   false, 0.4, 0.55, NULL),
    ('etr',   false, 0.4, 0.55, NULL),
    ('byd_2', false, 0.4, 0.55, NULL),
    ('err',   true,  0.85, 0.9, ARRAY['af','err','error','april fools'])
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    op.create_table(
        'difficulty_search_config',
        sa.Column(
            'difficulty',
            postgresql.ENUM(name='difficulty_class', create_type=False),
            nullable=False,
        ),
        sa.Column('hidden_from_broad', sa.Boolean(), nullable=False),
        sa.Column('min_similarity', sa.Float(), nullable=False),
        sa.Column('strong', sa.Float(), nullable=False),
        sa.Column('af_suffixes', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('difficulty'),
    )
    op.execute(sa.text(_SEED_CONFIG_SQL))

    op.execute(sa.text(_SEARCH_INDEX_SQL))
    # Exact-match B-tree on lower(term) resolves <=2-char aliases (O, mu) that
    # trigram cannot represent; the GIN trigram index powers fuzzy matching.
    op.execute(
        sa.text(
            "CREATE INDEX ix_search_index_term_trgm "
            "ON search_index USING gin (lower(term) gin_trgm_ops)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_search_index_term_lower "
            "ON search_index (lower(term))"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("DROP INDEX IF EXISTS ix_search_index_term_lower"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_search_index_term_trgm"))
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS search_index"))
    op.drop_table('difficulty_search_config')
    op.execute(sa.text("DROP EXTENSION IF EXISTS pg_trgm"))
