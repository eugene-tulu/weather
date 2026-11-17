#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 backups/weather-YYYYMMDDTHHMMSSZ.sql.gz" >&2
  exit 1
fi

USER="${POSTGRES_USER:-weather}"
DB="${POSTGRES_DB:-weather}"

gunzip -c "$1" | docker compose exec -T postgres psql -U "$USER" -d "$DB"
echo "Restored $1"
