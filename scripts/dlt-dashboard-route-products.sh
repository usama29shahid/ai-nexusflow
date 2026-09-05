#!/usr/bin/env bash
# Launch dlt Workspace Dashboard for Route products — pipeline metrics only.
# Use for loads, schema, trace, and local pipeline state under ~/.dlt/pipelines.
# Do NOT use the dashboard SQL / dataset browser against ClickHouse; query Bronze
# via CloudBeaver or clickhouse-client (see route README).
#
# Usage (repo root):
#   uv sync --extra dlt-dashboard   # once (includes dlt[hub] + marimo/…)
#   ./scripts/dlt-dashboard-route-products.sh
#   ./scripts/dlt-dashboard-route-products.sh --edit   # forwarded to `dlt … show`
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer a single instance so a second start does not silently bind the next port.
_stop_stale_dashboards() {
  local pids
  pids="$(pgrep -f 'marimo run .*/dlt/_workspace/helpers/dashboard/dlt_dashboard.py' 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "Stopping stale dlt dashboard process(es): ${pids}"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
  fi
  pids="$(pgrep -f '[d]lt pipeline --pipelines-dir .* route_products show' 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "Stopping stale dlt show process(es): ${pids}"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
  fi
}
_stop_stale_dashboards

PIPELINES_DIR="${DLT_PIPELINES_DIR:-${HOME}/.dlt/pipelines}"

echo "Opening dlt dashboard for route_products (pipeline metrics / schema / loads)."
echo "Not for ClickHouse data — use CloudBeaver or clickhouse-client for Bronze SQL."
echo "Ensure: uv sync --extra dlt-dashboard"
echo "If the browser shows a skew-protection warning: close old tabs and open the new URL."
exec uv run --extra dlt-dashboard dlt pipeline --pipelines-dir "${PIPELINES_DIR}" route_products show "$@"
