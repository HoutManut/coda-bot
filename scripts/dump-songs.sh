#!/usr/bin/env bash
# Dump the coda DB. Defaults to song/catalog tables only.
# Usage: scripts/dump-songs.sh [-v GAME_VERSION] [-a]
#   -v   game version tag for the filename, e.g. "6.14.0"
#   -a   dump all tables (full DB), not just song/catalog tables
# Connection comes from DATABASE_URL in .env (postgresql+asyncpg://user:pass@host:port/db).
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=""
ALL=0
while getopts "v:a" opt; do
  case "$opt" in
    v) VERSION="$OPTARG" ;;
    a) ALL=1 ;;
    *) echo "usage: $0 [-v GAME_VERSION] [-a]" >&2; exit 2 ;;
  esac
done

# Locate pg_dump (Homebrew postgresql@18 is not on PATH by default).
PG_DUMP="$(command -v pg_dump || true)"
[ -z "$PG_DUMP" ] && PG_DUMP="/opt/homebrew/opt/postgresql@18/bin/pg_dump"
[ -x "$PG_DUMP" ] || { echo "pg_dump not found" >&2; exit 1; }

# Read DATABASE_URL from .env.
[ -f .env ] || { echo ".env not found" >&2; exit 1; }
DB_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)"
[ -n "$DB_URL" ] || { echo "DATABASE_URL not set in .env" >&2; exit 1; }

# Strip the SQLAlchemy +asyncpg driver suffix so libpq understands the URL.
DB_URL="${DB_URL/+asyncpg/}"

SONG_TABLES=(
  songs song_difficulties
  artists artist_aliases artist_members
  charters charter_aliases
  packs song_aliases difficulty_aliases
  song_artists difficulty_artists song_charters difficulty_charters
  tags tag_categories song_tags difficulty_tags
  alembic_version
)

TBL_ARGS=()
if [ "$ALL" -eq 0 ]; then
  for t in "${SONG_TABLES[@]}"; do TBL_ARGS+=( -t "$t" ); done
fi

[ "$ALL" -eq 1 ] && PREFIX="coda" || PREFIX="coda-songs"

mkdir -p backups
if [ -n "$VERSION" ]; then
  OUT="backups/${PREFIX}-$(date +%Y%m%d)-v${VERSION}.dump"
else
  OUT="backups/${PREFIX}-$(date +%Y%m%d-%H%M%S).dump"
fi

"$PG_DUMP" -Fc ${TBL_ARGS[@]+"${TBL_ARGS[@]}"} -f "$OUT" "$DB_URL"
echo "wrote $OUT"
ls -lh "$OUT"
