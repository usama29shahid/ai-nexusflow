#!/usr/bin/env bash
# Prove MinIO IAM wiring for every Compose consumer that uses loader/reader.
# Usage (repo root, Vault rendered, MinIO up):
#   ./scripts/minio-iam-service-check.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

set -a
# shellcheck source=/dev/null
source "${ROOT}/.env"
# shellcheck source=scripts/load-secrets.sh
source "${ROOT}/scripts/load-secrets.sh"
set +a

if [[ "${NEXUS_SECRETS_BACKEND:-vault}" != "vault" ]]; then
  echo "Requires NEXUS_SECRETS_BACKEND=vault" >&2
  exit 1
fi

require() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing ${name}" >&2
    exit 1
  fi
}

require MINIO_LOADER_USER
require MINIO_LOADER_PASSWORD
require MINIO_READER_USER
require MINIO_READER_PASSWORD
require MINIO_PLATFORM_READER_USER
require MINIO_PLATFORM_READER_PASSWORD

env_name="${NEXUS_ENV:-dev}"
pass=0
fail=0

ok() {
  echo "  OK  $1"
  pass=$((pass + 1))
}

bad() {
  echo "  FAIL $1" >&2
  fail=$((fail + 1))
}

echo "=== MinIO IAM service check (NEXUS_ENV=${env_name}) ==="

echo
echo "[1/8] Policy bootstrap + multipart probe"
if ./scripts/minio-iam-bootstrap.sh; then
  ok "minio-iam-bootstrap (apply + probe)"
else
  bad "minio-iam-bootstrap (apply + probe)"
fi

echo
echo "[2/8] Host loader path (common.observability.lake)"
if uv run python - <<'PY'
from common.observability.lake import write_json_object

uri = write_json_object(
    "_iam_service_check/loader-lake.json",
    {"ok": True, "identity": "nexus_loader"},
)
assert uri.startswith("s3://nexus-telemetry-")
print(uri)
PY
then
  ok "observability lake S3 client uses loader"
else
  bad "observability lake S3 client"
fi

echo
echo "[3/8] Host reader path (lake-replay style get + marker put)"
if uv run python - <<'PY'
import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

env = os.environ["NEXUS_ENV"]
port = os.environ.get("MINIO_API_PORT", "9002")
endpoint = os.environ.get("MINIO_ENDPOINT_URL", f"http://localhost:{port}")
cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})

def client(ak, sk):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=ak,
        aws_secret_access_key=sk,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        config=cfg,
    )

reader = client(os.environ["MINIO_READER_USER"], os.environ["MINIO_READER_PASSWORD"])
telemetry = f"nexus-telemetry-{env}"
archive = f"nexus-dlt-dbt-clickhouse-{env}"
# get any object under probe/service prefix if present; put marker
marker = "_iam_service_check/reader-marker.txt"
reader.put_object(
    Bucket=telemetry,
    Key=f"indexes/signoz/{marker}",
    Body=b"marker",
)
try:
    reader.put_object(Bucket=archive, Key=marker, Body=b"nope")
except ClientError as exc:
    code = exc.response.get("Error", {}).get("Code", "")
    if code not in {"AccessDenied", "AccessDeniedException", "AllAccessDisabled"}:
        raise
else:
    raise SystemExit("reader must not put archive")
print("reader ok")
PY
then
  ok "reader marker + archive deny"
else
  bad "reader marker + archive deny"
fi

echo
echo "[4/8] OTel collector Compose env (loader)"
if docker compose ps otel-collector --status running -q 2>/dev/null | grep -q .; then
  ak="$(docker inspect otel-collector --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^AWS_ACCESS_KEY_ID=//p')"
  if [[ "${ak}" == "${MINIO_LOADER_USER}" ]]; then
    ok "otel-collector AWS_ACCESS_KEY_ID=${ak}"
  else
    bad "otel-collector AWS_ACCESS_KEY_ID='${ak}' (expected ${MINIO_LOADER_USER})"
  fi
else
  echo "  SKIP otel-collector not running"
fi

echo
echo "[5/8] Lakehouse Compose env (Polaris / Spark / Trino → loader)"
for svc in polaris spark-thrift trino; do
  if ! docker compose --profile lakehouse ps "${svc}" --status running -q 2>/dev/null | grep -q .; then
    echo "  SKIP ${svc} not running"
    continue
  fi
  envs="$(docker inspect "${svc}" --format '{{range .Config.Env}}{{println .}}{{end}}')"
  case "${svc}" in
    trino)
      ak="$(printf '%s\n' "${envs}" | sed -n 's/^MINIO_LOADER_USER=//p')"
      if [[ "${ak}" == "${MINIO_LOADER_USER}" ]]; then
        ok "trino MINIO_LOADER_USER=${ak}"
      else
        bad "trino MINIO_LOADER_USER='${ak}'"
      fi
      if printf '%s\n' "${envs}" | grep -q '^MINIO_ROOT_USER='; then
        bad "trino still has MINIO_ROOT_USER env"
      else
        ok "trino has no MINIO_ROOT_USER env"
      fi
      ;;
    *)
      ak="$(printf '%s\n' "${envs}" | sed -n 's/^AWS_ACCESS_KEY_ID=//p')"
      if [[ "${ak}" == "${MINIO_LOADER_USER}" ]]; then
        ok "${svc} AWS_ACCESS_KEY_ID=${ak}"
      else
        bad "${svc} AWS_ACCESS_KEY_ID='${ak}'"
      fi
      ;;
  esac
done

echo
echo "[6/8] In-network S3 put as loader (Compose network → minio:9000)"
# Reuse the pinned mc image (same as IAM apply) — no extra aws-cli pull.
network="$(docker inspect minio --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{break}}{{end}}')"
mc_image="${MINIO_MC_IMAGE:-quay.io/minio/aistor/mc:RELEASE.2026-09-06T02-44-40Z}"
if printf 'network-loader\n' | docker run --rm -i --network "${network}" \
  --entrypoint /bin/sh \
  -e MINIO_LOADER_USER \
  -e MINIO_LOADER_PASSWORD \
  -e NEXUS_ENV="${env_name}" \
  "${mc_image}" -c \
  'mc alias set n http://minio:9000 "$MINIO_LOADER_USER" "$MINIO_LOADER_PASSWORD" >/dev/null && mc pipe "n/nexus-telemetry-${NEXUS_ENV}/_iam_service_check/network-loader.txt"' \
  >/dev/null
then
  ok "in-network loader put via minio:9000 (mc)"
else
  bad "in-network loader put via minio:9000 (mc)"
fi

echo
echo "[7/8] Airflow remote logs connection (loader)"
if docker compose --profile airflow ps airflow-api-server --status running -q 2>/dev/null | grep -q .; then
  conn="$(docker inspect airflow-api-server --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^AIRFLOW_CONN_MINIO_LOGS=//p')"
  if [[ "${conn}" == *"${MINIO_LOADER_USER}"* ]]; then
    ok "airflow-api-server AIRFLOW_CONN_MINIO_LOGS uses loader user"
  else
    bad "airflow-api-server AIRFLOW_CONN_MINIO_LOGS missing loader user"
  fi
else
  echo "  SKIP Airflow not running"
fi

echo
echo "[8/8] Cleanup probe keys with root"
uv run python - <<'PY'
import os
import boto3
from botocore.config import Config

env = os.environ.get("NEXUS_ENV", "dev")
port = os.environ.get("MINIO_API_PORT", "9002")
endpoint = os.environ.get("MINIO_ENDPOINT_URL", f"http://localhost:{port}")
root = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["MINIO_ROOT_USER"],
    aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
prefix = "_iam_service_check/"
buckets = [
    f"nexus-telemetry-{env}",
    f"nexus-dlt-dbt-clickhouse-{env}",
    f"nexus-airflow-logs-{env}",
    f"nexus-dlt-dbt-spark-iceberg-archive-{env}",
    f"nexus-dlt-dbt-spark-iceberg-{env}",
]
for bucket in buckets:
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = root.list_objects_v2(**kwargs)
        for item in page.get("Contents") or []:
            root.delete_object(Bucket=bucket, Key=item["Key"])
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    # reader markers
    for pfx in (f"indexes/signoz/{prefix}", f"indexes/openobserve/{prefix}", f"indexes/openmetadata/{prefix}"):
        page = root.list_objects_v2(Bucket=bucket, Prefix=pfx) if bucket.endswith(f"telemetry-{env}") else {"Contents": []}
        for item in page.get("Contents") or []:
            root.delete_object(Bucket=bucket, Key=item["Key"])
print("cleanup ok")
PY
ok "root cleanup of _iam_service_check/"

echo
echo "=== Results: ${pass} passed, ${fail} failed ==="
if [[ "${fail}" -gt 0 ]]; then
  exit 1
fi
