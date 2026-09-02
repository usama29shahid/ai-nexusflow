#!/bin/sh
# Bootstrap Polaris catalog nexus_{NEXUS_ENV} on MinIO (lakehouse Iceberg warehouse).
set -eu

apk add --no-cache jq curl >/dev/null

SCRIPT_DIR=$(dirname "$0")
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/obtain-token.sh" POLARIS

CATALOG_NAME="${POLARIS_CATALOG_NAME:-nexus_dev}"
STORAGE_BUCKET="${POLARIS_WAREHOUSE_BUCKET:-nexus-dlt-dbt-spark-iceberg-dev}"
S3_ENDPOINT_EXTERNAL="${S3_ENDPOINT_EXTERNAL:-http://localhost:9002}"
S3_ENDPOINT_INTERNAL="${S3_ENDPOINT_INTERNAL:-http://minio:9000}"
AWS_REGION="${AWS_REGION:-us-east-1}"

STORAGE_LOCATION="s3://${STORAGE_BUCKET}/warehouse"
STORAGE_CONFIG_INFO=$(jq -n \
  --arg endpoint "${S3_ENDPOINT_EXTERNAL}" \
  --arg endpointInternal "${S3_ENDPOINT_INTERNAL}" \
  --arg region "${AWS_REGION}" \
  '{
    storageType: "S3",
    endpoint: $endpoint,
    endpointInternal: $endpointInternal,
    pathStyleAccess: true,
    region: $region
  }')

echo "Creating Polaris catalog ${CATALOG_NAME} at ${STORAGE_LOCATION}..."

PAYLOAD=$(jq -n \
  --arg name "${CATALOG_NAME}" \
  --arg location "${STORAGE_LOCATION}" \
  --argjson storage "${STORAGE_CONFIG_INFO}" \
  '{
    catalog: {
      name: $name,
      type: "INTERNAL",
      readOnly: false,
      properties: {
        "default-base-location": $location
      },
      storageConfigInfo: $storage
    }
  }')

# Create catalog (ignore if it already exists).
if curl --fail-with-body -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -H "Polaris-Realm: POLARIS" \
  "http://polaris:8181/api/management/v1/catalogs" \
  -d "${PAYLOAD}" >/dev/null 2>&1; then
  echo "Catalog ${CATALOG_NAME} created."
else
  echo "Catalog ${CATALOG_NAME} may already exist; continuing."
fi

echo "Granting catalog admin on ${CATALOG_NAME}..."
curl --fail-with-body -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -X PUT \
  "http://polaris:8181/api/management/v1/catalogs/${CATALOG_NAME}/catalog-roles/catalog_admin/grants" \
  -d '{"type":"catalog","privilege":"CATALOG_MANAGE_CONTENT"}' >/dev/null

# Spark Thrift sessions need nexus_dev.default; dbt uses schema gold (and layers below).
echo "Creating Iceberg namespaces in ${CATALOG_NAME}..."
for ns in default gold int marts pub raw_dlt_smoke stg_dlt_smoke raw_route stg_route; do
  if curl --fail-with-body -s \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -H "Polaris-Realm: POLARIS" \
    -X POST \
    "http://polaris:8181/api/catalog/v1/${CATALOG_NAME}/namespaces" \
    -d "{\"namespace\":[\"${ns}\"]}" >/dev/null 2>&1; then
    echo "  namespace ${ns} created"
  else
    echo "  namespace ${ns} may already exist"
  fi
done

touch /tmp/polaris-setup-done
echo "Polaris bootstrap complete (catalog=${CATALOG_NAME})."
