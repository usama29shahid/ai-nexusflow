#!/usr/bin/env bash
# pg_dump Supabase Postgres → local .nexusflow/backups/supabase/ → R2 bucket nexus-supabase-{env}.
# Uses the same Vault backup keys as ./scripts/backup-archive.sh (NEXUS_BACKUP_*).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a
fi

_pre_backup_endpoint="${NEXUS_BACKUP_ENDPOINT:-}"
_pre_backup_access="${NEXUS_BACKUP_ACCESS_KEY:-}"
_pre_backup_secret="${NEXUS_BACKUP_SECRET_KEY:-}"

if [[ -z "${NEXUS_BACKUP_ENDPOINT:-}" || -z "${NEXUS_BACKUP_ACCESS_KEY:-}" || -z "${NEXUS_BACKUP_SECRET_KEY:-}" ]]; then
  set -a
  # shellcheck source=scripts/load-secrets.sh
  source "${ROOT}/scripts/load-secrets.sh"
  set +a
fi
[[ -n "${_pre_backup_endpoint}" ]] && NEXUS_BACKUP_ENDPOINT="${_pre_backup_endpoint}"
[[ -n "${_pre_backup_access}" ]] && NEXUS_BACKUP_ACCESS_KEY="${_pre_backup_access}"
[[ -n "${_pre_backup_secret}" ]] && NEXUS_BACKUP_SECRET_KEY="${_pre_backup_secret}"

NEXUS_ENV="${NEXUS_ENV:-dev}"
NEXUS_BACKUP_ENDPOINT="${NEXUS_BACKUP_ENDPOINT%/}"
BUCKET="nexus-supabase-${NEXUS_ENV}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DAY="$(date -u +%Y/%m/%d)"
LOCAL_DIR="${ROOT}/.nexusflow/backups/supabase"
LOCAL_FILE="${LOCAL_DIR}/supabase-${STAMP}.dump"
OBJECT="dumps/${DAY}/supabase-${STAMP}.dump"

for v in NEXUS_BACKUP_ENDPOINT NEXUS_BACKUP_ACCESS_KEY NEXUS_BACKUP_SECRET_KEY; do
  if [[ -z "${!v:-}" ]]; then
    echo "${v} is empty. Put keys in Vault secret/nexusflow/${NEXUS_ENV}/backup" >&2
    exit 1
  fi
done

if ! docker inspect supabase-db >/dev/null 2>&1; then
  echo "supabase-db is not running." >&2
  exit 1
fi

mkdir -p "${LOCAL_DIR}"
echo "Dumping supabase-db → ${LOCAL_FILE}"
docker exec supabase-db pg_dump -U postgres -d postgres -Fc -f "/tmp/supabase-${STAMP}.dump"
docker cp "supabase-db:/tmp/supabase-${STAMP}.dump" "${LOCAL_FILE}"
docker exec supabase-db rm -f "/tmp/supabase-${STAMP}.dump"

# Keep 7 newest local dumps
ls -1t "${LOCAL_DIR}"/supabase-*.dump 2>/dev/null | tail -n +8 | xargs -r rm -f

network="$(docker inspect supabase-db --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{break}}{{end}}')"
image="${MINIO_MC_IMAGE:-quay.io/minio/aistor/mc:RELEASE.2026-09-06T02-44-40Z}"

echo "Uploading to ${NEXUS_BACKUP_ENDPOINT}/${BUCKET}/${OBJECT}"
docker run --rm \
  --network "${network}" \
  --entrypoint /bin/sh \
  -v "${LOCAL_FILE}:/dump.dump:ro" \
  -e NEXUS_BACKUP_ENDPOINT \
  -e NEXUS_BACKUP_ACCESS_KEY \
  -e NEXUS_BACKUP_SECRET_KEY \
  -e BUCKET="${BUCKET}" \
  -e OBJECT="${OBJECT}" \
  "${image}" -c '
set -eu
mc alias set backup "$NEXUS_BACKUP_ENDPOINT" "$NEXUS_BACKUP_ACCESS_KEY" "$NEXUS_BACKUP_SECRET_KEY" >/dev/null
# Same pattern as backup-archive.sh: Object Read & Write tokens often cannot CreateBucket.
if ! mc mb --ignore-existing "backup/${BUCKET}" 2>/tmp/mb.err; then
  if mc ls "backup/${BUCKET}" >/dev/null 2>&1; then
    echo "Bucket backup/${BUCKET} already exists (CreateBucket not permitted; continuing)."
  else
    echo "Cannot create or list backup/${BUCKET}." >&2
    echo "In Cloudflare R2: create bucket ${BUCKET} in this account, and grant the" >&2
    echo "NEXUS_BACKUP_* API token Object Read & Write on that bucket (same as archive buckets)." >&2
    cat /tmp/mb.err >&2 || true
    exit 1
  fi
fi
mc cp /dump.dump "backup/${BUCKET}/${OBJECT}"
'

echo "Supabase backup OK → ${BUCKET}/${OBJECT}"
