#!/usr/bin/env bash
# Source repo .env and, when NEXUS_SECRETS_BACKEND=vault, Agent-rendered secrets.
# Usage: source scripts/load-secrets.sh   (or: . scripts/load-secrets.sh)
set -a

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "Missing ${ROOT}/.env — copy from .env.example" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck source=/dev/null
source "${ROOT}/.env"

backend="${NEXUS_SECRETS_BACKEND:-env}"
if [[ "${backend}" == "vault" ]]; then
  secrets_file="${NEXUS_SECRETS_FILE:-${ROOT}/.nexusflow/secrets.env}"
  if [[ ! -f "${secrets_file}" ]]; then
    echo "NEXUS_SECRETS_BACKEND=vault but missing ${secrets_file}" >&2
    echo "Run: ./scripts/vault-bootstrap.sh" >&2
    return 1 2>/dev/null || exit 1
  fi
  # shellcheck source=/dev/null
  source "${secrets_file}"
fi

set +a
