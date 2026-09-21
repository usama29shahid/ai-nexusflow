#!/usr/bin/env bash
# Batch ingest: observability lake → reader native stores (SigNoz, OpenMetadata, Elementary).
#
# SigNoz target: implement under backlog item 2 (live OTLP already works via collector).
# OpenMetadata / Elementary targets: backlog items 3 / later — see docs/backlog.md.
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

Readers (implement per backlog — SigNoz = item 2):
  signoz         Replay lake OTLP batches into SigNoz
  openmetadata   Project lake + warehouse metadata into OpenMetadata
  elementary     Sync lake dbt artifacts into Elementary index

See docs/observability.md and docs/backlog.md
EOF
}

case "${target}" in
  help|-h|--help|"")
    usage
    exit 0
    ;;
  signoz|openmetadata|elementary)
    echo "Reader ingest for '${target}' is not implemented yet." >&2
    echo "Lake writes: MinIO nexus-telemetry-{env} (required). Live OTLP→SigNoz works when profile signoz is up." >&2
    echo "Implement lake→SigNoz under backlog item 2; see docs/backlog.md." >&2
    exit 2
    ;;
  *)
    echo "Unknown reader: ${target}" >&2
    usage
    exit 1
    ;;
esac
