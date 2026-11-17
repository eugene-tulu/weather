#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p backups
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="backups/weather-${STAMP}.sql.gz"
USER="${POSTGRES_USER:-weather}"
DB="${POSTGRES_DB:-weather}"

docker compose exec -T postgres pg_dump -U "$USER" "$DB" | gzip > "$FILE"
echo "Wrote $FILE"

if [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
  aws s3 cp "$FILE" "s3://${BACKUP_S3_BUCKET}/weather/${STAMP}.sql.gz"
  echo "Uploaded to s3://${BACKUP_S3_BUCKET}/weather/${STAMP}.sql.gz"
fi
