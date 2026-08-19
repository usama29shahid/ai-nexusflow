#!/bin/sh
# Obtain OAuth token from Apache Polaris (realm POLARIS).
set -eu

apk add --no-cache jq >/dev/null 2>&1 || true

realm="${1:-POLARIS}"

TOKEN=$(curl \
  --fail-with-body \
  -s \
  "http://polaris:8181/api/catalog/v1/oauth/tokens" \
  --user "${CLIENT_ID}:${CLIENT_SECRET}" \
  -H "Polaris-Realm: ${realm}" \
  -d grant_type=client_credentials \
  -d scope=PRINCIPAL_ROLE:ALL | jq -r .access_token)

if [ -z "${TOKEN}" ] || [ "${TOKEN}" = "null" ]; then
  echo "Failed to obtain Polaris access token." >&2
  exit 1
fi

export TOKEN
