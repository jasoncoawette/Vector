#!/bin/bash
# Hourly atomic snapshot of vector.db. Uses sqlite3's `.backup` so the
# backend can be writing concurrently — no quiescent window needed.
#
# Output:
#   $VECTOR_BACKUP_DIR/vector-YYYYMMDD-HHMM.db (default: ~/VectorBackups)
# Rotation:
#   Keeps the newest $VECTOR_BACKUP_KEEP files (default 48 -> 2 days).

set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_DIR"

if [[ -f backend/.env ]]; then
    set -a
    # shellcheck disable=SC1091
    source backend/.env
    set +a
fi

WORKSPACE="${VECTOR_WORKSPACE:-$HOME/VectorWorkspace}"
DB="$WORKSPACE/vector.db"
BACKUP_DIR="${VECTOR_BACKUP_DIR:-$HOME/VectorBackups}"
KEEP="${VECTOR_BACKUP_KEEP:-48}"

if [[ ! -f "$DB" ]]; then
    echo "no db at $DB; skipping snapshot" >&2
    exit 0
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%d-%H%M)"
TARGET="$BACKUP_DIR/vector-$STAMP.db"

# .backup uses the online backup API — safe with WAL writers active.
sqlite3 "$DB" ".backup '$TARGET'"

# Rotate: list newest -> oldest, keep the first KEEP, delete the rest.
# shellcheck disable=SC2012
ls -1t "$BACKUP_DIR"/vector-*.db 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
    rm -f "$old"
done

echo "snapshot ok -> $TARGET"
