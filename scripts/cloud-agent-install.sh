#!/usr/bin/env bash
# Idempotent repository bootstrap for Cloud Agents.
# Infra containers are started in cloud-agent-start.sh, not here.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Created .env from .env.example."
  else
    echo "Missing .env and .env.example." >&2
    exit 1
  fi
fi

export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

echo "Syncing Python environment..."
uv sync

DBT_PROFILES_DIR="${HOME}/.dbt"
DBT_PROFILES_FILE="${DBT_PROFILES_DIR}/profiles.yml"
if [[ ! -f "${DBT_PROFILES_FILE}" ]]; then
  mkdir -p "${DBT_PROFILES_DIR}"
  cat > "${DBT_PROFILES_FILE}" <<'EOF'
nexus_clickhouse:
  target: dev
  outputs:
    dev:
      type: clickhouse
      host: "{{ env_var('CLICKHOUSE_HOST', 'localhost') }}"
      port: "{{ env_var('CLICKHOUSE_HTTP_PORT', '8123') | as_number }}"
      user: "{{ env_var('CLICKHOUSE_USER', 'default') }}"
      password: "{{ env_var('CLICKHOUSE_PASSWORD') }}"
      schema: "{{ env_var('CLICKHOUSE_DB', 'warehouse') }}"
      secure: false

nexus_lakehouse:
  target: dev
  outputs:
    dev:
      type: spark
      method: thrift
      host: "{{ env_var('SPARK_THRIFT_HOST', 'localhost') }}"
      port: "{{ env_var('SPARK_THRIFT_PORT', '10000') | as_number }}"
      user: "{{ env_var('SPARK_THRIFT_USER', 'dbt') }}"
      schema: gold
      threads: 4
EOF
  echo "Created ${DBT_PROFILES_FILE}."
fi

echo "Install complete."
