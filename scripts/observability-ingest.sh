#!/usr/bin/env bash
# Batch ingest: observability lake → reader native stores (SigNoz, OpenMetadata, Elementary).
#
# SigNoz (backlog item 2): live OTLP via collector + lake replay below.
# OpenMetadata / Elementary: backlog items 3 / later — see docs/backlog.md.
#
# Usage (from repo root):
#   ./scripts/observability-ingest.sh signoz
#   ./scripts/observability-ingest.sh signoz -- --since 2026-09-24T00:00:00Z --force
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
  openmetadata   Project lake + warehouse metadata into OpenMetadata (item 3)
  elementary     Sync lake dbt artifacts into Elementary index (later)

SigNoz examples:
  ./scripts/observability-ingest.sh signoz
  ./scripts/observability-ingest.sh signoz -- --since 2026-09-24T00:00:00Z
  ./scripts/observability-ingest.sh signoz -- --force --dry-run

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
    # Allow: observability-ingest.sh signoz -- --since ...
    if [[ "${1:-}" == "--" ]]; then
      shift
    fi
    chmod +x scripts/signoz-ensure.sh
    # Skip ensure's AUTO_REPLAY — this script runs lake ingest next (avoids double force-replay).
    SIGNOZ_ENSURE_SKIP_AUTO_REPLAY=1 ./scripts/signoz-ensure.sh
    exec uv run python scripts/signoz_lake_ingest.py "$@"
    ;;
  openmetadata|elementary)
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
