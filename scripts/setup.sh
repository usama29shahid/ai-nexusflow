#!/usr/bin/env bash
# Bootstrap on WSL, Hostinger VPS, or AWS EC2.
# Infra → Docker Compose. Python (uv, DLT, dbt) → host, never inside Compose.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit secrets if needed."
  else
    echo "Missing .env and .env.example." >&2
    exit 1
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH." >&2
  echo "WSL: enable Docker Desktop → Settings → Resources → WSL Integration → Ubuntu." >&2
  echo "VPS/EC2: install Docker Engine, then re-run this script." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required (docker compose)." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is installed but not on PATH. Add ~/.local/bin to PATH and re-run." >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source .env
set +a
# Existing .env files may omit this; both branches is the default dev stack.
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-clickhouse,lakehouse}"

echo "Starting infrastructure (COMPOSE_PROFILES=${COMPOSE_PROFILES})..."
docker compose up -d

echo "Syncing Python environment on the host..."
uv sync

if [[ ",${COMPOSE_PROFILES}," == *",lakehouse,"* ]]; then
  echo "Lakehouse profile: re-registering Iceberg smoke table (Polaris in-memory catalog)..."
  wait_healthy() {
    local service="$1"
    for _ in $(seq 1 60); do
      if docker compose ps "${service}" 2>/dev/null | grep -q "(healthy)"; then
        return 0
      fi
      sleep 2
    done
    echo "Timed out waiting for ${service}." >&2
    return 1
  }
  wait_healthy polaris-setup
  set +e
  uv run python tests/integration/register_lakehouse_smoke.py
  register_rc=$?
  set -e
  case "${register_rc}" in
    0)
      echo "  Iceberg smoke table registered."
      ;;
    2)
      echo "  No Iceberg smoke files in MinIO yet (first-time OK)."
      echo "  After uv run python tests/integration/dlt_lakehouse_smoke.py, run ./scripts/lakehouse-restore.sh"
      ;;
    *)
      echo "  Failed to re-register Iceberg smoke table in Polaris (exit ${register_rc})." >&2
      echo "  Lakehouse queries will fail until: ./scripts/lakehouse-restore.sh" >&2
      exit 1
      ;;
  esac
fi

echo
echo "Done."
echo "  Profiles:   ${COMPOSE_PROFILES} (MinIO always)"
echo "  ClickHouse: curl http://localhost:8123/ping"
echo "  MinIO UI:   http://localhost:9001"
echo "  Polaris:    http://localhost:8181"
echo "  Trino UI:   http://localhost:8080"
echo "  Spark Thrift: localhost:10000 (dbt-spark)"
echo "  Python:     uv run python --version"
