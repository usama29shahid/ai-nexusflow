#!/usr/bin/env bash
# Batch ingest: observability lake → reader native stores (SigNoz, OpenObserve, …).
#
# SigNoz (backlog item 2): live OTLP via collector + lake replay below.
# OpenObserve (backlog item 2.1): live OTLP via collector + lake replay below.
# OpenMetadata (backlog item 3): ClickHouse warehouse + lake dbt artifacts.
# Elementary: later — see docs/backlog.md.
#
# Usage (from repo root):
#   ./scripts/observability-ingest.sh signoz
#   ./scripts/observability-ingest.sh signoz -- --since 2026-09-24T00:00:00Z --force
#   ./scripts/observability-ingest.sh openobserve
#   ./scripts/observability-ingest.sh openmetadata
#   ./scripts/observability-ingest.sh elementary
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

target="${1:-}"
shift || true

usage() {
  cat <<'EOF'
Usage: ./scripts/observability-ingest.sh <reader> [-- <reader-args>]

Readers:
  signoz         Replay lake OTLP batches into SigNoz (item 2)
  openobserve    Replay lake OTLP batches into OpenObserve (item 2.1)
  openmetadata   Catalog ClickHouse + lake dbt into OpenMetadata (item 3)
  elementary     Sync lake dbt artifacts into Elementary index (later)

SigNoz examples:
  ./scripts/observability-ingest.sh signoz
  ./scripts/observability-ingest.sh signoz -- --since 2026-09-24T00:00:00Z
  ./scripts/observability-ingest.sh signoz -- --force --dry-run

OpenObserve examples:
  ./scripts/observability-ingest.sh openobserve
  ./scripts/observability-ingest.sh openobserve -- --force --since 2026-09-01T00:00:00Z
  ./scripts/observability-ingest.sh openobserve -- --signals traces,events --force
  ./scripts/observability-ingest.sh openobserve -- --signals traces,logs,metrics,events

OpenMetadata examples:
  ./scripts/observability-ingest.sh openmetadata
  ./scripts/observability-ingest.sh openmetadata -- --force
  ./scripts/observability-ingest.sh openmetadata -- --run-id local-2026-09-27T12:00:00Z
  ./scripts/observability-ingest.sh openmetadata -- --skip-dbt

See docs/observability.md and docs/backlog.md
EOF
}

case "${target}" in
  help|-h|--help|"")
    usage
    exit 0
    ;;
  signoz)
    if [[ -f .env ]]; then
      set -a
      # shellcheck source=/dev/null
      source .env
      set +a
    fi
    if [[ -f scripts/load-secrets.sh ]]; then
      set -a
      # shellcheck source=/dev/null
      source scripts/load-secrets.sh 2>/dev/null || true
      set +a
    fi
    if [[ "${1:-}" == "--" ]]; then
      shift
    fi
    chmod +x scripts/signoz-ensure.sh
    SIGNOZ_ENSURE_SKIP_AUTO_REPLAY=1 ./scripts/signoz-ensure.sh
    exec uv run python scripts/signoz_lake_ingest.py "$@"
    ;;
  openobserve)
    if [[ -f .env ]]; then
      set -a
      # shellcheck source=/dev/null
      source .env
      set +a
    fi
    if [[ -f scripts/load-secrets.sh ]]; then
      set -a
      # shellcheck source=/dev/null
      source scripts/load-secrets.sh 2>/dev/null || true
      set +a
    fi
    if [[ "${1:-}" == "--" ]]; then
      shift
    fi
    # shellcheck source=scripts/openobserve-credentials.sh
    source "${ROOT}/scripts/openobserve-credentials.sh"
    ensure_openobserve_env_credentials
    exec uv run python scripts/openobserve_lake_ingest.py "$@"
    ;;
  openmetadata)
    if [[ -f .env ]]; then
      set -a
      # shellcheck source=/dev/null
      source .env
      set +a
    fi
    if [[ -f scripts/load-secrets.sh ]]; then
      set -a
      # shellcheck source=/dev/null
      source scripts/load-secrets.sh 2>/dev/null || true
      set +a
    fi
    if [[ "${1:-}" == "--" ]]; then
      shift
    fi
    # shellcheck source=scripts/openmetadata-credentials.sh
    source "${ROOT}/scripts/openmetadata-credentials.sh"
    ensure_openmetadata_env_credentials
    exec uv run python scripts/openmetadata_lake_ingest.py "$@"
    ;;
  elementary)
    echo "Reader ingest for '${target}' is not implemented yet." >&2
    echo "Lake writes: MinIO nexus-telemetry-{env} (required)." >&2
    echo "Implement under the matching backlog item; see docs/backlog.md." >&2
    exit 2
    ;;
  *)
    echo "Unknown reader: ${target}" >&2
    usage
    exit 1
    ;;
esac
