#!/usr/bin/env bash
# Batch ingest: observability lake → reader native stores (SigNoz, OpenMetadata, Elementary).
#
# Reader Compose profiles are not wired yet. This script is the future entrypoint for
# lake replay / projection into tool indexes without changing pipeline emit code.
#
# Usage (from repo root, when implemented):
#   ./scripts/observability-ingest.sh signoz
#   ./scripts/observability-ingest.sh openmetadata
#   ./scripts/observability-ingest.sh elementary
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

target="${1:-}"

usage() {
  cat <<'EOF'
Usage: ./scripts/observability-ingest.sh <reader>

Readers (not implemented yet):
  signoz         Replay lake OTLP batches into SigNoz
  openmetadata   Project lake + warehouse metadata into OpenMetadata
  elementary     Sync lake dbt artifacts into Elementary index

See docs/observability.md
EOF
}

case "${target}" in
  help|-h|--help|"")
    usage
    exit 0
    ;;
  signoz|openmetadata|elementary)
    echo "Reader ingest for '${target}' is not implemented yet." >&2
    echo "Start MinIO + otel-collector; pipeline runs write to nexus-telemetry-{env}." >&2
    echo "Enable the ${target} Compose profile when it is added to docker-compose.yml." >&2
    exit 2
    ;;
  *)
    echo "Unknown reader: ${target}" >&2
    usage
    exit 1
    ;;
esac
