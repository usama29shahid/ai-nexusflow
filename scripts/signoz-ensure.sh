#!/usr/bin/env bash
# Ensure SigNoz standalone can ingest OTLP (internal ClickHouse + ingester).
#
# signoz/signoz-standalone sometimes boots with UI healthy while the internal
# clickhouse user / telemetrystore / ingester never come up — collector then
# cannot reach signoz:4317. This script repairs that state idempotently.
#
# Does NOT provision dashboards (see signoz-bootstrap.sh) and does NOT stop the UI.
# SIGNOZ_AUTO_REPLAY=1 replays lake OTLP when the trace index is empty, unless
# SIGNOZ_ENSURE_SKIP_AUTO_REPLAY=1 (set by observability-ingest.sh to avoid double ingest).
#
# Usage (from repo root):
#   ./scripts/signoz-ensure.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OTLP_WAIT_SECS="${SIGNOZ_OTLP_WAIT_SECS:-180}"

if ! docker compose --profile signoz ps signoz --status running -q 2>/dev/null | grep -q .; then
  echo "ERROR: SigNoz is not running. Start with: ./scripts/start.sh signoz" >&2
  exit 2
fi

echo "Ensuring SigNoz telemetrystore + OTLP ingester..."
docker compose --profile signoz exec -T signoz sh -c '
set -e
if ! id clickhouse >/dev/null 2>&1; then
  echo "Creating missing clickhouse user/group..."
  groupadd -f clickhouse
  if ! id clickhouse >/dev/null 2>&1; then
    useradd -r -g clickhouse -s /bin/false clickhouse
  fi
fi
mkdir -p /var/lib/clickhouse /run/clickhouse
chown -R clickhouse:clickhouse /var/lib/clickhouse /run/clickhouse 2>/dev/null || true
# Keeper before server; migrator before ingester.
systemctl start signoz-telemetrykeeper-clickhousekeeper-0.service 2>/dev/null || true
systemctl start signoz-telemetrystore-clickhouse-0-0.service 2>/dev/null || true
i=0
while [ "$i" -lt 60 ]; do
  if curl -sf "http://127.0.0.1:8123/ping" >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 2
done
if ! curl -sf "http://127.0.0.1:8123/ping" >/dev/null 2>&1; then
  echo "ERROR: SigNoz internal ClickHouse HTTP :8123 did not become ready" >&2
  systemctl --no-pager -l status signoz-telemetrystore-clickhouse-0-0.service || true
  exit 1
fi
systemctl start signoz-telemetrystore-migrator.service 2>/dev/null || true
systemctl start signoz-ingester.service 2>/dev/null || true
'

echo "Waiting up to ${OTLP_WAIT_SECS}s for SigNoz OTLP HTTP :4318..."
deadline=$((SECONDS + OTLP_WAIT_SECS))
while (( SECONDS < deadline )); do
  if docker compose --profile signoz exec -T signoz \
    curl -sf -o /dev/null -X POST "http://127.0.0.1:4318/v1/traces" \
    -H "Content-Type: application/json" \
    -d '{"resourceSpans":[]}' 2>/dev/null; then
    echo "SigNoz OTLP ready (http://signoz:4317 gRPC / :4318 HTTP)."

    # Soft warning: empty index after wipe/recreate (lake still has history).
    trace_n="$(docker compose --profile signoz exec -T signoz \
      clickhouse-client --query "SELECT count() FROM signoz_traces.distributed_signoz_index_v3" 2>/dev/null || echo "?")"
    if [[ "${trace_n}" == "0" ]]; then
      echo "WARNING: SigNoz trace index is empty (common after volume recreate / cold start)." >&2
      echo "  Replay lake (example last 14d):" >&2
      echo "  ./scripts/observability-ingest.sh signoz -- --force --since \$(python3 -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(days=14)).strftime(\"%Y-%m-%dT%H:%M:%SZ\"))')" >&2
      if [[ "${SIGNOZ_AUTO_REPLAY:-0}" == "1" && "${SIGNOZ_ENSURE_SKIP_AUTO_REPLAY:-0}" != "1" ]]; then
        echo "SIGNOZ_AUTO_REPLAY=1 — running lake replay..."
        since="$(python3 -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
        if [[ -f .env ]]; then
          set -a
          # shellcheck source=/dev/null
          source .env
          set +a
        fi
        uv run python scripts/signoz_lake_ingest.py --force --since "${since}"
      fi
    fi
    exit 0
  fi
  sleep 3
done

echo "ERROR: SigNoz OTLP :4318 did not become ready." >&2
echo "Check: docker exec signoz systemctl status signoz-ingester signoz-telemetrystore-clickhouse-0-0" >&2
exit 1
