#!/usr/bin/env bash
# Reader bootstrap: upsert Route products dashboard into SigNoz.
#
# Pipeline code never calls SigNoz. Prefer REST (API key or login).
# SQLite metastore edits are OFF by default (they stop the UI and previously
# caused readonly DB / outage). Enable only with SIGNOZ_BOOTSTRAP_SQLITE=1.
#
# Usage:
#   ./scripts/signoz-bootstrap.sh
#   SIGNOZ_API_KEY=... ./scripts/signoz-bootstrap.sh
#   SIGNOZ_BOOTSTRAP_SQLITE=1 ./scripts/signoz-bootstrap.sh   # local last resort
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

UI_PORT="${SIGNOZ_UI_PORT:-3301}"
UI_BASE="http://127.0.0.1:${UI_PORT}"
DASHBOARD_JSON="${ROOT}/docker/signoz/dashboards/route-products.json"
DASHBOARD_TITLE="Nexus Route products"
STABLE_DASHBOARD_ID="$(python3 -c 'import uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "https://nexusflow.local/signoz/dashboards/route-products"))')"

chmod +x scripts/signoz-ensure.sh
./scripts/signoz-ensure.sh

if [[ ! -f "${DASHBOARD_JSON}" ]]; then
  echo "ERROR: missing dashboard JSON: ${DASHBOARD_JSON}" >&2
  exit 1
fi

auth_header=()
if [[ -n "${SIGNOZ_API_KEY:-}" ]]; then
  auth_header=(-H "SIGNOZ-API-KEY: ${SIGNOZ_API_KEY}")
  echo "Using SIGNOZ_API_KEY for dashboard API."
elif [[ -n "${SIGNOZ_EMAIL:-}" && -n "${SIGNOZ_PASSWORD:-}" ]]; then
  echo "Logging into SigNoz as ${SIGNOZ_EMAIL}..."
  login_resp="$(curl -sf -X POST "${UI_BASE}/api/v1/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":$(python3 -c 'import json,os; print(json.dumps(os.environ["SIGNOZ_EMAIL"]))'),\"password\":$(python3 -c 'import json,os; print(json.dumps(os.environ["SIGNOZ_PASSWORD"]))')}" \
    || true)"
  token="$(python3 -c '
import json,sys
raw=sys.stdin.read().strip()
if not raw:
  raise SystemExit(0)
try:
  data=json.loads(raw)
except json.JSONDecodeError:
  raise SystemExit(0)
for key in ("accessJwt","accessToken","token"):
  if isinstance(data.get(key), str) and data[key]:
    print(data[key]); raise SystemExit(0)
inner=data.get("data") or {}
if isinstance(inner, dict):
  for key in ("accessJwt","accessToken","token"):
    if isinstance(inner.get(key), str) and inner[key]:
      print(inner[key]); raise SystemExit(0)
' <<<"${login_resp}" || true)"
  if [[ -n "${token}" ]]; then
    auth_header=(-H "Authorization: Bearer ${token}")
  fi
fi

payload="$(python3 - <<'PY' "${DASHBOARD_JSON}" "${DASHBOARD_TITLE}"
import json, sys
path, title = sys.argv[1], sys.argv[2]
doc = json.load(open(path, encoding="utf-8"))
doc["title"] = title
doc.setdefault("uploadedGrafana", False)
print(json.dumps({"data": doc}))
PY
)"

tmp_list="$(mktemp)"
tmp_create="$(mktemp)"
cleanup_api() { rm -f "${tmp_list}" "${tmp_create}"; }
trap cleanup_api EXIT

if ((${#auth_header[@]})); then
  list_code="$(curl -s -o "${tmp_list}" -w "%{http_code}" \
    "${UI_BASE}/api/v1/dashboards" "${auth_header[@]}" || true)"
  existing_id=""
  if [[ "${list_code}" == "200" ]]; then
    existing_id="$(python3 - <<'PY' "${DASHBOARD_TITLE}" "${tmp_list}"
import json,sys
title, path = sys.argv[1], sys.argv[2]
try:
  payload=json.load(open(path, encoding="utf-8"))
except Exception:
  raise SystemExit(0)
rows=payload.get("data") if isinstance(payload, dict) else payload
if not isinstance(rows, list):
  raise SystemExit(0)
for row in rows:
  if not isinstance(row, dict):
    continue
  data=row.get("data") if isinstance(row.get("data"), dict) else row
  t=(data or {}).get("title") or row.get("title") or ""
  if t == title:
    print(row.get("uuid") or row.get("id") or "")
    break
PY
)"
  fi
  api_failed=0
  if [[ -n "${existing_id}" ]]; then
    # Re-apply repo JSON so panel/query edits in route-products.json take effect.
    update_code="$(curl -s -o "${tmp_create}" -w "%{http_code}" \
      -X PUT "${UI_BASE}/api/v1/dashboards/${existing_id}" \
      -H "Content-Type: application/json" \
      "${auth_header[@]}" \
      -d "${payload}" || true)"
    if [[ "${update_code}" == "200" || "${update_code}" == "201" ]]; then
      echo "Updated dashboard via API (id=${existing_id}): ${DASHBOARD_TITLE}"
      echo "Open: ${UI_BASE}/dashboard/${existing_id}"
      exit 0
    fi
    # Never DELETE on update failure — a failed recreate would wipe a working dashboard.
    echo "WARNING: dashboard API update returned HTTP ${update_code}; leaving existing dashboard in place." >&2
    api_failed=1
  else
    create_code="$(curl -s -o "${tmp_create}" -w "%{http_code}" \
      -X POST "${UI_BASE}/api/v1/dashboards" \
      -H "Content-Type: application/json" \
      "${auth_header[@]}" \
      -d "${payload}" || true)"
    if [[ "${create_code}" == "200" || "${create_code}" == "201" ]]; then
      new_id="$(python3 -c '
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8"))
d=p.get("data") if isinstance(p, dict) else p
if isinstance(d, dict):
  print(d.get("uuid") or d.get("id") or "")
' "${tmp_create}" || true)"
      echo "Created dashboard via API: ${DASHBOARD_TITLE}"
      echo "Open: ${UI_BASE}/dashboard/${new_id:-}"
      exit 0
    fi
    echo "WARNING: dashboard API create returned HTTP ${create_code}." >&2
    api_failed=1
  fi
fi

if [[ "${SIGNOZ_BOOTSTRAP_SQLITE:-0}" != "1" ]]; then
  if [[ "${api_failed:-0}" == "1" ]]; then
    echo "ERROR: dashboard API create/update failed; existing dashboard (if any) was left unchanged." >&2
    echo "  Retry with a working SIGNOZ_API_KEY, or:" >&2
    echo "  SIGNOZ_BOOTSTRAP_SQLITE=1 ./scripts/signoz-bootstrap.sh" >&2
    echo "  Or import manually: ${DASHBOARD_JSON}" >&2
    exit 1
  fi
  echo "Dashboard not provisioned via API (no SIGNOZ_API_KEY / login)." >&2
  echo "  Set SIGNOZ_API_KEY or SIGNOZ_EMAIL/SIGNOZ_PASSWORD, or import:" >&2
  echo "  ${DASHBOARD_JSON}" >&2
  echo "  Last resort (stops UI briefly): SIGNOZ_BOOTSTRAP_SQLITE=1 ./scripts/signoz-bootstrap.sh" >&2
  exit 0
fi

echo "SIGNOZ_BOOTSTRAP_SQLITE=1 — upserting via metastore (stops SigNoz UI briefly)..."
host_db="$(mktemp /tmp/signoz-db.XXXXXX.db)"
cleanup_all() { rm -f "${host_db}" "${tmp_list}" "${tmp_create}"; }
trap cleanup_all EXIT

docker compose --profile signoz exec -T signoz systemctl stop signoz-signoz.service >/dev/null
# Clean stop should checkpoint; drop leftover WAL so we do not mix host/container files.
docker compose --profile signoz exec -T signoz sh -c \
  'rm -f /var/lib/signoz/signoz.db-wal /var/lib/signoz/signoz.db-shm; sleep 1'
docker cp signoz:/var/lib/signoz/signoz.db "${host_db}"

action_id="$(python3 - <<'PY' "${host_db}" "${DASHBOARD_JSON}" "${DASHBOARD_TITLE}" "${STABLE_DASHBOARD_ID}"
import json, sqlite3, sys
from datetime import datetime, timezone

db_path, dash_path, title, stable_id = sys.argv[1:5]
doc = json.load(open(dash_path, encoding="utf-8"))
doc["title"] = title
doc.setdefault("uploadedGrafana", False)
data_json = json.dumps(doc, separators=(",", ":"))
now = datetime.now(timezone.utc).isoformat()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
org = conn.execute("select id from organizations limit 1").fetchone()
user = conn.execute(
    "select email from users where status='active' order by is_root desc limit 1"
).fetchone()
if org is None or user is None:
    raise SystemExit(
        "SigNoz metastore has no org/user yet — complete first UI signup, then re-run bootstrap"
    )
org_id, email = org["id"], user["email"]

row = conn.execute("select id from dashboard where id = ?", (stable_id,)).fetchone()
if row is None:
    for candidate in conn.execute("select id, data from dashboard"):
        try:
            payload = json.loads(candidate["data"] or "{}")
        except json.JSONDecodeError:
            continue
        if payload.get("title") == title:
            row = candidate
            break

if row is not None:
    conn.execute(
        "update dashboard set updated_at=?, updated_by=?, data=? where id=?",
        (now, email, data_json, row["id"]),
    )
    print(f"updated:{row['id']}")
else:
    conn.execute(
        "insert into dashboard (id, created_at, updated_at, created_by, updated_by, data, locked, org_id) "
        "values (?,?,?,?,?,?,?,?)",
        (stable_id, now, now, email, email, data_json, 0, org_id),
    )
    print(f"created:{stable_id}")
conn.commit()
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
conn.close()
PY
)"

docker cp "${host_db}" signoz:/var/lib/signoz/signoz.db
docker compose --profile signoz exec -T signoz sh -c '
set -e
chown signoz:signoz /var/lib/signoz/signoz.db
chmod 664 /var/lib/signoz/signoz.db
# Fail closed if the query user cannot write (prevents readonly-database boot loop).
su -s /bin/sh signoz -c "test -w /var/lib/signoz/signoz.db"
rm -f /var/lib/signoz/signoz.db-wal /var/lib/signoz/signoz.db-shm
'
docker compose --profile signoz exec -T signoz systemctl start signoz-signoz.service >/dev/null

for _ in $(seq 1 60); do
  if curl -sf "${UI_BASE}/api/v1/health" >/dev/null; then
    break
  fi
  sleep 2
done
curl -sf "${UI_BASE}/api/v1/health" >/dev/null

dash_id="${action_id#*:}"
echo "Dashboard ${action_id%%:*} via SQLite: ${DASHBOARD_TITLE}"
echo "Open: ${UI_BASE}/dashboard/${dash_id}"
