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

echo "Starting infrastructure..."
docker compose up -d

echo "Syncing Python environment on the host..."
uv sync

echo
echo "Done."
echo "  ClickHouse: curl http://localhost:8123/ping"
echo "  MinIO UI:   http://localhost:9001"
echo "  Python:     uv run python --version"
