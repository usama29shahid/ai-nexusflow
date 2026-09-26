#!/usr/bin/env bash
# Reader bootstrap: upsert all JSON dashboards under docker/signoz/dashboards/.
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
DASHBOARD_DIR="${ROOT}/docker/signoz/dashboards"

chmod +x scripts/signoz-ensure.sh
./scripts/signoz-ensure.sh

mapfile -t DASHBOARD_FILES < <(find "${DASHBOARD_DIR}" -maxdepth 1 -type f -name '*.json' | sort)
if ((${#DASHBOARD_FILES[@]} == 0)); then
  echo "ERROR: no dashboard JSON under ${DASHBOARD_DIR}" >&2
  exit 1
fi

# Standalone image is currently v0.117.x — V2 (schemaVersion v6) crashes the Dashboards UI.
# Also refuse layout/widget drift and dual collector-config ops drift.
chmod +x scripts/check-observability-static.sh
./scripts/check-observability-static.sh

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

dashboard_title() {
  python3 - <<'PY' "$1"
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
doc = json.load(open(path, encoding="utf-8"))
title = doc.get("title")
if isinstance(title, str) and title.strip():
    print(title.strip()); raise SystemExit(0)
display = ((doc.get("spec") or {}) if isinstance(doc.get("spec"), dict) else {}).get("display") or {}
name = display.get("name") if isinstance(display, dict) else None
if isinstance(name, str) and name.strip():
    print(name.strip()); raise SystemExit(0)
print(path.stem.replace("-", " ").title())
PY
}

dashboard_payload() {
  python3 - <<'PY' "$1" "$2"
import json, sys
path, title = sys.argv[1], sys.argv[2]
doc = json.load(open(path, encoding="utf-8"))
if doc.get("schemaVersion"):
    spec = doc.setdefault("spec", {})
    if isinstance(spec, dict):
        display = spec.setdefault("display", {})
        if isinstance(display, dict):
            display["name"] = title
else:
    doc["title"] = title
    doc.setdefault("uploadedGrafana", False)
# SigNoz stores the request JSON as the dashboard document. Do NOT wrap in
# {"data": ...} — that nests title/spec and the UI shows blank dashboards.
print(json.dumps(doc))
PY
}

stable_dashboard_id() {
  python3 - <<'PY' "$1"
import pathlib, sys, uuid
stem = pathlib.Path(sys.argv[1]).stem
print(uuid.uuid5(uuid.NAMESPACE_URL, f"https://nexusflow.local/signoz/dashboards/{stem}"))
PY
}

upsert_via_api() {
  local dash_path="$1"
  local title="$2"
  local payload
  payload="$(dashboard_payload "${dash_path}" "${title}")"

  local tmp_list tmp_create
  tmp_list="$(mktemp)"
  tmp_create="$(mktemp)"

  local list_code existing_id
  list_code="$(curl -s -o "${tmp_list}" -w "%{http_code}" \
    "${UI_BASE}/api/v1/dashboards" "${auth_header[@]}" || true)"
  existing_id=""
  if [[ "${list_code}" == "200" ]]; then
    existing_id="$(python3 - <<'PY' "${title}" "${tmp_list}"
import json,sys
title, path = sys.argv[1], sys.argv[2]
try:
  payload=json.load(open(path, encoding="utf-8"))
except Exception:
  raise SystemExit(0)
rows=payload.get("data") if isinstance(payload, dict) else payload
if not isinstance(rows, list):
  raise SystemExit(0)

def row_title(row):
  if not isinstance(row, dict):
    return ""
  data = row.get("data") if isinstance(row.get("data"), dict) else row
  if not isinstance(data, dict):
    return ""
  t = data.get("title") or row.get("title") or ""
  if isinstance(t, str) and t.strip():
    return t.strip()
  # Recover from older bootstrap bug that stored {"data": <doc>} as the document.
  inner = data.get("data") if isinstance(data.get("data"), dict) else None
  if isinstance(inner, dict):
    t = inner.get("title") or ""
    if isinstance(t, str) and t.strip():
      return t.strip()
    display = ((inner.get("spec") or {}) if isinstance(inner.get("spec"), dict) else {}).get("display") or {}
    name = display.get("name") if isinstance(display, dict) else ""
    if isinstance(name, str) and name.strip():
      return name.strip()
  display = ((data.get("spec") or {}) if isinstance(data.get("spec"), dict) else {}).get("display") or {}
  name = display.get("name") if isinstance(display, dict) else ""
  return name.strip() if isinstance(name, str) else ""

for row in rows:
  if row_title(row) == title:
    print(row.get("uuid") or row.get("id") or "")
    break
PY
)"
  fi

  local code=0
  if [[ -n "${existing_id}" ]]; then
    code="$(curl -s -o "${tmp_create}" -w "%{http_code}" \
      -X PUT "${UI_BASE}/api/v1/dashboards/${existing_id}" \
      -H "Content-Type: application/json" \
      "${auth_header[@]}" \
      -d "${payload}" || true)"
    if [[ "${code}" == "200" || "${code}" == "201" ]]; then
      echo "Updated dashboard via API (id=${existing_id}): ${title}"
      echo "Open: ${UI_BASE}/dashboard/${existing_id}"
      rm -f "${tmp_list}" "${tmp_create}"
      return 0
    fi
    echo "WARNING: dashboard API update returned HTTP ${code}; leaving existing dashboard in place: ${title}" >&2
    rm -f "${tmp_list}" "${tmp_create}"
    return 1
  fi

  code="$(curl -s -o "${tmp_create}" -w "%{http_code}" \
    -X POST "${UI_BASE}/api/v1/dashboards" \
    -H "Content-Type: application/json" \
    "${auth_header[@]}" \
    -d "${payload}" || true)"
  if [[ "${code}" == "200" || "${code}" == "201" ]]; then
    local new_id
    new_id="$(python3 -c '
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8"))
d=p.get("data") if isinstance(p, dict) else p
if isinstance(d, dict):
  print(d.get("uuid") or d.get("id") or "")
' "${tmp_create}" || true)"
    echo "Created dashboard via API: ${title}"
    echo "Open: ${UI_BASE}/dashboard/${new_id:-}"
    rm -f "${tmp_list}" "${tmp_create}"
    return 0
  fi
  echo "WARNING: dashboard API create returned HTTP ${code}: ${title}" >&2
  rm -f "${tmp_list}" "${tmp_create}"
  return 1
}

upsert_via_sqlite() {
  local dash_path="$1"
  local title="$2"
  local stable_id="$3"
  local host_db="$4"

  python3 - <<'PY' "${host_db}" "${dash_path}" "${title}" "${stable_id}"
import json, sqlite3, sys
from datetime import datetime, timezone

db_path, dash_path, title, stable_id = sys.argv[1:5]
doc = json.load(open(dash_path, encoding="utf-8"))
if doc.get("schemaVersion"):
    spec = doc.setdefault("spec", {})
    if isinstance(spec, dict):
        display = spec.setdefault("display", {})
        if isinstance(display, dict):
            display["name"] = title
else:
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

def stored_title(raw: str) -> str:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return ""
    t = payload.get("title") or ""
    if isinstance(t, str) and t.strip():
        return t.strip()
    display = ((payload.get("spec") or {}) if isinstance(payload.get("spec"), dict) else {}).get("display") or {}
    name = display.get("name") if isinstance(display, dict) else ""
    return name.strip() if isinstance(name, str) else ""

row = conn.execute("select id from dashboard where id = ?", (stable_id,)).fetchone()
if row is None:
    for candidate in conn.execute("select id, data from dashboard"):
        if stored_title(candidate["data"]) == title:
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
}

api_ok=0
api_fail=0
if ((${#auth_header[@]})); then
  for dash_path in "${DASHBOARD_FILES[@]}"; do
    title="$(dashboard_title "${dash_path}")"
    if upsert_via_api "${dash_path}" "${title}"; then
      api_ok=$((api_ok + 1))
    else
      api_fail=$((api_fail + 1))
    fi
  done
  if ((api_fail == 0)); then
    echo "Bootstrapped ${api_ok} dashboard(s) via API."
    exit 0
  fi
fi

if [[ "${SIGNOZ_BOOTSTRAP_SQLITE:-0}" != "1" ]]; then
  if ((api_fail > 0)); then
    echo "ERROR: ${api_fail} of $((api_ok + api_fail)) dashboard API upsert(s) failed (${api_ok} succeeded)." >&2
    echo "  Successful PUTs/POSTs in this run already applied; failed titles were left at their previous content." >&2
    echo "  Retry with a working SIGNOZ_API_KEY, or:" >&2
    echo "  SIGNOZ_BOOTSTRAP_SQLITE=1 ./scripts/signoz-bootstrap.sh" >&2
    echo "  Or import manually from: ${DASHBOARD_DIR}" >&2
    exit 1
  fi
  echo "Dashboards not provisioned via API (no SIGNOZ_API_KEY / login)." >&2
  echo "  Set SIGNOZ_API_KEY or SIGNOZ_EMAIL/SIGNOZ_PASSWORD, or import from:" >&2
  echo "  ${DASHBOARD_DIR}" >&2
  echo "  Last resort (stops UI briefly): SIGNOZ_BOOTSTRAP_SQLITE=1 ./scripts/signoz-bootstrap.sh" >&2
  exit 0
fi

echo "SIGNOZ_BOOTSTRAP_SQLITE=1 — upserting via metastore (stops SigNoz UI briefly)..."
host_db="$(mktemp /tmp/signoz-db.XXXXXX.db)"
signoz_ui_stopped=0
restart_signoz_ui_if_stopped() {
  if ((signoz_ui_stopped)); then
    echo "Restarting SigNoz UI after SQLite bootstrap interrupt..." >&2
    docker compose --profile signoz exec -T signoz systemctl start signoz-signoz.service >/dev/null 2>&1 || true
    signoz_ui_stopped=0
  fi
}
cleanup_all() {
  restart_signoz_ui_if_stopped
  rm -f "${host_db}"
}
trap cleanup_all EXIT

docker compose --profile signoz exec -T signoz systemctl stop signoz-signoz.service >/dev/null
signoz_ui_stopped=1
docker compose --profile signoz exec -T signoz sh -c \
  'rm -f /var/lib/signoz/signoz.db-wal /var/lib/signoz/signoz.db-shm; sleep 1'
docker cp signoz:/var/lib/signoz/signoz.db "${host_db}"

for dash_path in "${DASHBOARD_FILES[@]}"; do
  title="$(dashboard_title "${dash_path}")"
  stable_id="$(stable_dashboard_id "${dash_path}")"
  action_id="$(upsert_via_sqlite "${dash_path}" "${title}" "${stable_id}" "${host_db}")"
  dash_id="${action_id#*:}"
  echo "Dashboard ${action_id%%:*} via SQLite: ${title}"
  echo "Open: ${UI_BASE}/dashboard/${dash_id}"
done

docker cp "${host_db}" signoz:/var/lib/signoz/signoz.db
docker compose --profile signoz exec -T signoz sh -c '
set -e
chown signoz:signoz /var/lib/signoz/signoz.db
chmod 664 /var/lib/signoz/signoz.db
su -s /bin/sh signoz -c "test -w /var/lib/signoz/signoz.db"
rm -f /var/lib/signoz/signoz.db-wal /var/lib/signoz/signoz.db-shm
'
docker compose --profile signoz exec -T signoz systemctl start signoz-signoz.service >/dev/null

for _ in $(seq 1 60); do
  if curl -sf "${UI_BASE}/api/v1/health" >/dev/null; then
    signoz_ui_stopped=0
    echo "Bootstrapped ${#DASHBOARD_FILES[@]} dashboard(s) via SQLite."
    exit 0
  fi
  sleep 2
done
curl -sf "${UI_BASE}/api/v1/health" >/dev/null
signoz_ui_stopped=0
echo "Bootstrapped ${#DASHBOARD_FILES[@]} dashboard(s) via SQLite."
