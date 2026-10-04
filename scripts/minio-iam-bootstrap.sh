#!/usr/bin/env bash
# Create MinIO IAM users from Vault-rendered env and probe the policies.
# Usage (from repo root, Vault already unsealed and Agent rendered):
#   ./scripts/minio-iam-bootstrap.sh              # apply + probe
#   ./scripts/minio-iam-bootstrap.sh --apply-only # apply only (start.sh path)
#
# Refuses NEXUS_SECRETS_BACKEND=env. Passwords are not written to a file.
# Root (MINIO_ROOT_*) creates the users. Apps use loader / reader / platform_reader.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

APPLY_ONLY=0
if [[ "${1:-}" == "--apply-only" ]]; then
  APPLY_ONLY=1
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--apply-only]" >&2
  exit 1
fi

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "Missing ${ROOT}/.env — copy from .env.example" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "${ROOT}/.env"
# shellcheck source=scripts/load-secrets.sh
source "${ROOT}/scripts/load-secrets.sh"
set +a

if [[ "${NEXUS_SECRETS_BACKEND:-vault}" != "vault" ]]; then
  echo "MinIO IAM keys live in Vault. Set NEXUS_SECRETS_BACKEND=vault and run ./scripts/start.sh vault" >&2
  exit 1
fi

require_secret() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "${name} is empty. Run ./scripts/start.sh vault so Agent renders secrets.env" >&2
    exit 1
  fi
}

require_secret MINIO_ROOT_USER
require_secret MINIO_ROOT_PASSWORD
require_secret MINIO_LOADER_USER
require_secret MINIO_LOADER_PASSWORD
require_secret MINIO_READER_USER
require_secret MINIO_READER_PASSWORD
require_secret MINIO_PLATFORM_READER_USER
require_secret MINIO_PLATFORM_READER_PASSWORD
require_secret MINIO_ADMIN_USER
require_secret MINIO_ADMIN_PASSWORD

NEXUS_ENV="${NEXUS_ENV:-dev}"
export NEXUS_ENV

if ! docker inspect minio >/dev/null 2>&1; then
  echo "MinIO container is not running. Start it with ./scripts/start.sh minio" >&2
  exit 1
fi

# First attached network only (multi-network concat breaks --network).
network="$(docker inspect minio --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{break}}{{end}}')"
if [[ -z "${network}" ]]; then
  echo "Could not resolve the Compose network for container minio." >&2
  exit 1
fi

image="${MINIO_MC_IMAGE:-quay.io/minio/aistor/mc:RELEASE.2026-09-06T02-44-40Z}"
work="$(mktemp -d)"
cleanup() {
  rm -rf "${work}"
}
trap cleanup EXIT

uv run python scripts/minio_iam_policies.py --env "${NEXUS_ENV}" --out "${work}"

echo "Applying MinIO IAM for NEXUS_ENV=${NEXUS_ENV}..."
docker run --rm \
  --network "${network}" \
  --entrypoint /bin/sh \
  -v "${work}:/policies:ro" \
  -v "${ROOT}/docker/minio/iam/apply.sh:/apply.sh:ro" \
  -e MINIO_ROOT_USER \
  -e MINIO_ROOT_PASSWORD \
  -e MINIO_LOADER_USER \
  -e MINIO_LOADER_PASSWORD \
  -e MINIO_READER_USER \
  -e MINIO_READER_PASSWORD \
  -e MINIO_PLATFORM_READER_USER \
  -e MINIO_PLATFORM_READER_PASSWORD \
  -e MINIO_ADMIN_USER \
  -e MINIO_ADMIN_PASSWORD \
  "${image}" /apply.sh

if [[ "${APPLY_ONLY}" -eq 0 ]]; then
  echo "Probing loader, reader, platform_reader, and admin policies..."
  uv run python scripts/minio_iam_probe.py
  echo "MinIO IAM bootstrap OK (nexus_loader, nexus_reader, nexus_platform_reader, nexus_admin)."
else
  echo "MinIO IAM users applied (probe skipped; run ./scripts/minio-iam-bootstrap.sh to verify)."
fi
