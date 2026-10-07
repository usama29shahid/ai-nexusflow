#!/usr/bin/env bash
# Mirror MinIO REST archive buckets to S3-compatible off-site storage (e.g. Cloudflare R2).
# Same bucket names and object keys as MinIO. Never uses --remove (R2 keeps history).
#
# Usage (from repo root; MinIO running; Vault Agent rendered for loader creds):
#   ./scripts/backup-archive.sh
#
# Requires Vault KV secret/nexusflow/{env}/backup → Agent secrets.env:
#   NEXUS_BACKUP_ENDPOINT, NEXUS_BACKUP_ACCESS_KEY, NEXUS_BACKUP_SECRET_KEY
# (optional first seed from .env via vault-bootstrap; prefer Vault only after cutover)
#
# See docs/operations.md (archive backup / restore).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "Missing ${ROOT}/.env — copy from .env.example" >&2
  exit 1
fi

# Airflow / nexus-elt inject via --env-file before this script runs. Capture
# non-empty values so an empty NEXUS_BACKUP_*= line in .env cannot wipe them.
_pre_backup_endpoint="${NEXUS_BACKUP_ENDPOINT:-}"
_pre_backup_access="${NEXUS_BACKUP_ACCESS_KEY:-}"
_pre_backup_secret="${NEXUS_BACKUP_SECRET_KEY:-}"
_pre_loader_user="${MINIO_LOADER_USER:-}"
_pre_loader_password="${MINIO_LOADER_PASSWORD:-}"

set -a
# shellcheck source=/dev/null
source "${ROOT}/.env"
set +a

[[ -n "${_pre_backup_endpoint}" ]] && NEXUS_BACKUP_ENDPOINT="${_pre_backup_endpoint}"
[[ -n "${_pre_backup_access}" ]] && NEXUS_BACKUP_ACCESS_KEY="${_pre_backup_access}"
[[ -n "${_pre_backup_secret}" ]] && NEXUS_BACKUP_SECRET_KEY="${_pre_backup_secret}"
[[ -n "${_pre_loader_user}" ]] && MINIO_LOADER_USER="${_pre_loader_user}"
[[ -n "${_pre_loader_password}" ]] && MINIO_LOADER_PASSWORD="${_pre_loader_password}"
export NEXUS_BACKUP_ENDPOINT NEXUS_BACKUP_ACCESS_KEY NEXUS_BACKUP_SECRET_KEY
export MINIO_LOADER_USER MINIO_LOADER_PASSWORD

# Only load Vault Agent secrets.env when backup/loader secrets are still missing.
if [[ -z "${NEXUS_BACKUP_ENDPOINT:-}" || -z "${NEXUS_BACKUP_ACCESS_KEY:-}" || -z "${NEXUS_BACKUP_SECRET_KEY:-}" || -z "${MINIO_LOADER_USER:-}" || -z "${MINIO_LOADER_PASSWORD:-}" ]]; then
  set -a
  # shellcheck source=scripts/load-secrets.sh
  source "${ROOT}/scripts/load-secrets.sh"
  set +a
fi

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "${name} is empty. Put endpoint/access_key/secret_key in Vault:" >&2
    echo "  vault kv put secret/nexusflow/\${NEXUS_ENV}/backup endpoint=… access_key=… secret_key=…" >&2
    echo "Then: ./scripts/start.sh vault and ./scripts/start.sh airflow (refresh elt env)." >&2
    exit 1
  fi
}

require_secret() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "${name} is empty. Run ./scripts/start.sh vault so Agent renders secrets.env" >&2
    exit 1
  fi
}

require_var NEXUS_BACKUP_ENDPOINT
require_var NEXUS_BACKUP_ACCESS_KEY
require_var NEXUS_BACKUP_SECRET_KEY
require_secret MINIO_LOADER_USER
require_secret MINIO_LOADER_PASSWORD

NEXUS_ENV="${NEXUS_ENV:-dev}"
export NEXUS_ENV

# Strip trailing slash so mc alias URLs stay clean.
NEXUS_BACKUP_ENDPOINT="${NEXUS_BACKUP_ENDPOINT%/}"
export NEXUS_BACKUP_ENDPOINT

if ! docker inspect minio >/dev/null 2>&1; then
  echo "MinIO container is not running. Start it with ./scripts/start.sh minio" >&2
  exit 1
fi

network="$(docker inspect minio --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{break}}{{end}}')"
if [[ -z "${network}" ]]; then
  echo "Could not resolve the Compose network for container minio." >&2
  exit 1
fi

image="${MINIO_MC_IMAGE:-quay.io/minio/aistor/mc:RELEASE.2026-09-06T02-44-40Z}"

warehouse_archive="nexus-dlt-dbt-clickhouse-${NEXUS_ENV}"
lakehouse_archive="nexus-dlt-dbt-spark-iceberg-archive-${NEXUS_ENV}"

echo "Backing up archive buckets to ${NEXUS_BACKUP_ENDPOINT} (NEXUS_ENV=${NEXUS_ENV})..."
echo "  - ${warehouse_archive}"
echo "  - ${lakehouse_archive}"

docker run --rm \
  --network "${network}" \
  --entrypoint /bin/sh \
  -e MINIO_LOADER_USER \
  -e MINIO_LOADER_PASSWORD \
  -e NEXUS_BACKUP_ENDPOINT \
  -e NEXUS_BACKUP_ACCESS_KEY \
  -e NEXUS_BACKUP_SECRET_KEY \
  -e NEXUS_ENV \
  -e warehouse_archive="${warehouse_archive}" \
  -e lakehouse_archive="${lakehouse_archive}" \
  "${image}" -c '
set -eu
mc alias set local http://minio:9000 "$MINIO_LOADER_USER" "$MINIO_LOADER_PASSWORD" >/dev/null
mc alias set backup "$NEXUS_BACKUP_ENDPOINT" "$NEXUS_BACKUP_ACCESS_KEY" "$NEXUS_BACKUP_SECRET_KEY" >/dev/null
for b in "$warehouse_archive" "$lakehouse_archive"; do
  # Object Read & Write tokens often cannot CreateBucket — create buckets in the
  # Cloudflare UI first, or use an Admin Read & Write R2 token.
  if ! mc mb --ignore-existing "backup/${b}" 2>/tmp/mb.err; then
    if mc ls "backup/${b}" >/dev/null 2>&1; then
      echo "Bucket backup/${b} already exists (CreateBucket not permitted; continuing)."
    else
      echo "Cannot create or access backup/${b}." >&2
      echo "Create it in the Cloudflare R2 UI (exact name), or use an R2 API token" >&2
      echo "with Admin Read & Write / permission to create buckets." >&2
      cat /tmp/mb.err >&2 || true
      exit 1
    fi
  fi
  # No --remove: destination keeps objects that source no longer has.
  mc mirror --overwrite "local/${b}" "backup/${b}"
done
'

echo "Archive backup OK (NEXUS_ENV=${NEXUS_ENV} → ${NEXUS_BACKUP_ENDPOINT})"
