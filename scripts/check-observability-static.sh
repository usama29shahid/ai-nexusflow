#!/usr/bin/env bash
# Static checks for SigNoz + OpenObserve dashboards and OTel base ops (no Docker).
# Used by signoz-bootstrap.sh; safe alone: ./scripts/check-observability-static.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SIGNOZ_DIR="${ROOT}/docker/signoz/dashboards"
OO_DIR="${ROOT}/docker/openobserve/dashboards"
OTEL_BASE="${ROOT}/docker/otel/collector-config.yaml"

python3 - <<'PY' "${SIGNOZ_DIR}" "${OO_DIR}" "${OTEL_BASE}" "${ROOT}/scripts/render-otel-collector-config.py"
import json, pathlib, re, sys

signoz_dir, oo_dir, base_path, render_path = map(pathlib.Path, sys.argv[1:5])
errors: list[str] = []

# --- SigNoz V1 dashboards ---
signoz_files = sorted(signoz_dir.glob("*.json"))
if not signoz_files:
    errors.append(f"no SigNoz dashboard JSON under {signoz_dir}")

for path in signoz_files:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"signoz/{path.name}: invalid JSON ({exc})")
        continue
    if doc.get("schemaVersion"):
        errors.append(
            f"signoz/{path.name}: V2 dashboard (schemaVersion set); standalone needs V1"
        )
        continue
    title = doc.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"signoz/{path.name}: missing V1 title")
    widgets = doc.get("widgets")
    layout = doc.get("layout")
    if not isinstance(widgets, list) or not widgets:
        errors.append(f"signoz/{path.name}: missing widgets[]")
        continue
    if not isinstance(layout, list) or not layout:
        errors.append(f"signoz/{path.name}: missing layout[]")
        continue
    wids = {str(w.get("id")) for w in widgets if isinstance(w, dict)}
    lids = {str(item.get("i")) for item in layout if isinstance(item, dict)}
    if wids != lids:
        errors.append(
            f"signoz/{path.name}: layout/widget id mismatch "
            f"(only_in_widgets={sorted(wids - lids)} only_in_layout={sorted(lids - wids)})"
        )

# --- OpenObserve dashboards (schema version 5) ---
oo_files = sorted(oo_dir.glob("*.json")) if oo_dir.is_dir() else []
if not oo_files:
    errors.append(f"no OpenObserve dashboard JSON under {oo_dir}")

for path in oo_files:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"openobserve/{path.name}: invalid JSON ({exc})")
        continue
    title = doc.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"openobserve/{path.name}: missing title")
    ver = doc.get("version")
    if ver not in (5, "5"):
        errors.append(f"openobserve/{path.name}: expected version 5, got {ver!r}")

# --- OTel base config ---
base = base_path.read_text(encoding="utf-8")
if "prometheus/self:" not in base:
    errors.append(f"{base_path.name}: missing prometheus/self")
if "docker_stats:" not in base:
    errors.append(f"{base_path.name}: missing docker_stats receiver")
if "prometheus/clickhouse:" in base:
    errors.append(
        f"{base_path.name}: prometheus/clickhouse belongs in render inject "
        "(not always-on base — CH profile may be stopped)"
    )
if 'host: "127.0.0.1"' not in base or "port: 8888" not in base:
    errors.append(f"{base_path.name}: prometheus reader must bind 127.0.0.1:8888")
if "receivers: [otlp, prometheus/self, docker_stats]" not in base:
    errors.append(
        f"{base_path.name}: metrics pipeline should default to "
        "otlp + prometheus/self + docker_stats (CH scrape via render)"
    )

render_src = render_path.read_text(encoding="utf-8")
if "CLICKHOUSE_RECEIVER" not in render_src or "clickhouse:9363" not in render_src:
    errors.append("render-otel-collector-config.py: missing ClickHouse scrape inject")

expected = {
    "http://minio:9000/minio/health/live",
    "http://otel-collector:13133",
}
# Restrict to httpcheck block
hc = re.search(r"(?ms)^  httpcheck:.*?^(?=processors:)", base)
if not hc:
    errors.append(f"{base_path.name}: missing httpcheck block")
else:
    endpoints = set(re.findall(r"- (http://\S+)", hc.group(0)))
    if not expected.issubset(endpoints):
        errors.append(
            f"{base_path.name}: missing always-on httpcheck endpoints "
            f"{sorted(expected - endpoints)}"
        )
    extra = endpoints - expected
    if extra:
        errors.append(
            f"{base_path.name}: unexpected httpcheck endpoints {sorted(extra)} "
            "(always-on only)"
        )

if errors:
    print("ERROR: observability static checks failed:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    raise SystemExit(1)
print(
    f"Observability static checks OK "
    f"(signoz={len(signoz_files)} openobserve={len(oo_files)} dashboards; "
    f"otel base ops)."
)
PY
