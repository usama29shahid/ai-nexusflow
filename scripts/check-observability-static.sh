#!/usr/bin/env bash
# Static checks for SigNoz dashboards + OTel ops receiver sync (no Docker required).
# Used by signoz-bootstrap.sh; safe to run alone: ./scripts/check-observability-static.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DASHBOARD_DIR="${ROOT}/docker/signoz/dashboards"
OTEL_BASE="${ROOT}/docker/otel/collector-config.yaml"
OTEL_SIGNOZ="${ROOT}/docker/otel/collector-config.signoz.yaml"

python3 - <<'PY' "${DASHBOARD_DIR}" "${OTEL_BASE}" "${OTEL_SIGNOZ}"
import json, pathlib, re, sys

dash_dir, base_path, signoz_path = map(pathlib.Path, sys.argv[1:4])
errors: list[str] = []

files = sorted(dash_dir.glob("*.json"))
if not files:
    errors.append(f"no dashboard JSON under {dash_dir}")

for path in files:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name}: invalid JSON ({exc})")
        continue
    if doc.get("schemaVersion"):
        errors.append(
            f"{path.name}: V2 dashboard (schemaVersion set); standalone needs V1 title+widgets+layout"
        )
        continue
    title = doc.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{path.name}: missing V1 title")
    widgets = doc.get("widgets")
    layout = doc.get("layout")
    if not isinstance(widgets, list) or not widgets:
        errors.append(f"{path.name}: missing widgets[]")
        continue
    if not isinstance(layout, list) or not layout:
        errors.append(f"{path.name}: missing layout[]")
        continue
    wids = {str(w.get("id")) for w in widgets if isinstance(w, dict)}
    lids = {str(item.get("i")) for item in layout if isinstance(item, dict)}
    if wids != lids:
        errors.append(
            f"{path.name}: layout/widget id mismatch "
            f"(only_in_widgets={sorted(wids - lids)} only_in_layout={sorted(lids - wids)})"
        )

ops_pattern = re.compile(
    r"(?ms)^  prometheus/self:.*?^  resource/uptime:.*?^        action: upsert\n",
)
telemetry_pattern = re.compile(
    r"(?ms)^  telemetry:.*?^                port: 8888\n",
)

def ops_blob(text: str, label: str) -> str | None:
    m = ops_pattern.search(text)
    if not m:
        errors.append(f"{label}: missing prometheus/self + resource/uptime ops block")
        return None
    return m.group(0)

def telemetry_blob(text: str, label: str) -> str | None:
    m = telemetry_pattern.search(text)
    if not m:
        errors.append(f"{label}: missing telemetry prometheus reader block")
        return None
    blob = m.group(0)
    if 'host: "127.0.0.1"' not in blob:
        errors.append(f"{label}: prometheus reader host must be 127.0.0.1 (not published)")
    return blob

base = base_path.read_text(encoding="utf-8")
signoz = signoz_path.read_text(encoding="utf-8")
ob, os_ = ops_blob(base, base_path.name), ops_blob(signoz, signoz_path.name)
tb, ts = telemetry_blob(base, base_path.name), telemetry_blob(signoz, signoz_path.name)
if ob is not None and os_ is not None and ob != os_:
    errors.append(
        f"ops receivers/processors differ between {base_path.name} and {signoz_path.name}"
    )
if tb is not None and ts is not None and tb != ts:
    errors.append(
        f"telemetry prometheus reader differs between {base_path.name} and {signoz_path.name}"
    )

# Always-on httpcheck endpoints only (optional profiles intentionally omitted).
expected = {
    "http://minio:9000/minio/health/live",
    "http://otel-collector:13133",
}
for label, text in ((base_path.name, base), (signoz_path.name, signoz)):
    endpoints = set(re.findall(r"- (http://\S+)", text))
    # Only consider httpcheck block endpoints (both files share the same list today).
    if not expected.issubset(endpoints):
        errors.append(f"{label}: missing always-on httpcheck endpoints {sorted(expected - endpoints)}")
    extra = endpoints - expected
    # Allow other http:// mentions outside httpcheck (none expected today).
    if extra:
        errors.append(f"{label}: unexpected http endpoints {sorted(extra)} (always-on only)")

if errors:
    print("ERROR: observability static checks failed:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    raise SystemExit(1)
print(f"Observability static checks OK ({len(files)} dashboard(s), collector ops in sync).")
PY
