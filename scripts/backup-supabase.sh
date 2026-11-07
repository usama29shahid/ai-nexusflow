#!/usr/bin/env bash
# pg_dump Supabase Postgres → MinIO bucket nexus-supabase-{env} (local S3).
# Off-site R2 copy is ./scripts/backup-archive.sh / Airflow DAG ops_backup_archive.
#
# Airflow runs this inside nexus-elt with host docker.sock. Capture injected
# MINIO_LOADER_* before sourcing .env. Nested docker -v uses NEXUS_REPO_ROOT
# (host path) for the temp dump file.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

_pre_loader_user="${MINIO_LOADER_USER:-}"
_pre_loader_password="${MINIO_LOADER_PASSWORD:-}"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a
fi

[[ -n "${_pre_loader_user}" ]] && MINIO_LOADER_USER="${_pre_loader_user}"
[[ -n "${_pre_loader_password}" ]] && MINIO_LOADER_PASSWORD="${_pre_loader_password}"

if [[ -z "${MINIO_LOADER_USER:-}" || -z "${MINIO_LOADER_PASSWORD:-}" ]]; then
  set -a
  # shellcheck source=scripts/load-secrets.sh
  source "${ROOT}/scripts/load-secrets.sh"
  set +a
fi

NEXUS_ENV="${NEXUS_ENV:-dev}"
BUCKET="nexus-supabase-${NEXUS_ENV}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DAY="$(date -u +%Y/%m/%d)"
OBJECT="dumps/${DAY}/supabase-${STAMP}.dump"
TMP_DIR="${ROOT}/.nexusflow/tmp/supabase"
TMP_FILE="${TMP_DIR}/supabase-${STAMP}.dump"
# Nested Docker: daemon resolves -v paths on the host.
HOST_ROOT="${NEXUS_REPO_ROOT:-${ROOT}}"
HOST_FILE="${HOST_ROOT}/.nexusflow/tmp/supabase/supabase-${STAMP}.dump"
image="${MINIO_MC_IMAGE:-quay.io/minio/aistor/mc:RELEASE.2026-09-06T02-44-40Z}"

for v in MINIO_LOADER_USER MINIO_LOADER_PASSWORD; do
  if [[ -z "${!v:-}" ]]; then
    echo "${v} is empty. Run ./scripts/start.sh vault so Agent renders secrets.env" >&2
    exit 1
  fi
done
export MINIO_LOADER_USER MINIO_LOADER_PASSWORD

if ! docker inspect supabase-db >/dev/null 2>&1; then
  echo "supabase-db is not running." >&2
  exit 1
fi

if ! docker inspect minio >/dev/null 2>&1; then
  echo "MinIO container is not running. Start it with ./scripts/start.sh minio" >&2
  exit 1
fi

# docker cp writes as root on the host. Reclaim so the EXIT trap can delete
# the temp dump. In nexus-elt, NEXUS_REPO_ROOT is a host path and is not visible
# here — ownership is taken from ROOT (/workspace bind mount). Nested docker -v
# still uses the host path for the daemon.
reclaim_host_path() {
  local path="$1"
  [[ -e "${path}" ]] || return 0
  local uid gid host_path
  uid="$(stat -c '%u' "${ROOT}")"
  gid="$(stat -c '%g' "${ROOT}")"
  if chown -R "${uid}:${gid}" "${path}" 2>/dev/null; then
    return 0
  fi
  host_path="${path}"
  if [[ -n "${NEXUS_REPO_ROOT:-}" && "${path}" == "${ROOT}"/* ]]; then
    host_path="${NEXUS_REPO_ROOT}/${path#"${ROOT}"/}"
  fi
  docker run --rm \
    -v "${host_path}:/target" \
    --entrypoint /bin/sh \
    "${image}" \
    -c "chown -R ${uid}:${gid} /target"
}

mkdir -p "${TMP_DIR}"
cleanup_tmp() {
  if [[ -e "${TMP_FILE}" ]]; then
    reclaim_host_path "${TMP_FILE}" 2>/dev/null || true
    rm -f "${TMP_FILE}" 2>/dev/null || true
  fi
}
trap cleanup_tmp EXIT

echo "Dumping supabase-db → temp ${TMP_FILE}"
docker exec supabase-db pg_dump -U postgres -d postgres -Fc -f "/tmp/supabase-${STAMP}.dump"
docker cp "supabase-db:/tmp/supabase-${STAMP}.dump" "${TMP_FILE}"
docker exec supabase-db rm -f "/tmp/supabase-${STAMP}.dump"
reclaim_host_path "${TMP_FILE}"

network="$(docker inspect minio --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{break}}{{end}}')"
if [[ -z "${network}" ]]; then
  echo "Could not resolve the Compose network for container minio." >&2
  exit 1
fi

echo "Uploading to minio/${BUCKET}/${OBJECT}"
docker run --rm \
  --network "${network}" \
  --entrypoint /bin/sh \
  -v "${HOST_FILE}:/dump.dump:ro" \
  -e MINIO_LOADER_USER \
  -e MINIO_LOADER_PASSWORD \
  -e BUCKET="${BUCKET}" \
  -e OBJECT="${OBJECT}" \
  "${image}" -c '
set -eu
mc alias set local http://minio:9000 "$MINIO_LOADER_USER" "$MINIO_LOADER_PASSWORD" >/dev/null
if ! mc ls "local/${BUCKET}" >/dev/null 2>&1; then
  echo "MinIO bucket ${BUCKET} is missing. Re-run minio-init / ./scripts/start.sh" >&2
  exit 1
fi
mc cp /dump.dump "local/${BUCKET}/${OBJECT}"
'

echo "Supabase backup OK → minio/${BUCKET}/${OBJECT}"
echo "Off-site: ./scripts/backup-archive.sh or Airflow DAG ops_backup_archive"
