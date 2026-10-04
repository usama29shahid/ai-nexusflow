#!/bin/sh
# Apply MinIO IAM users inside the Compose network. Invoked by
# scripts/minio-iam-bootstrap.sh with policy JSON mounted at /policies.
# Passwords arrive as env vars; this script does not write them to disk.
#
# AIStor mc (MINIO_MC_IMAGE pin in docker-compose.yml / minio-iam-bootstrap.sh)
# treats `policy create` and `user add` as upserts — update policy JSON and
# secrets without remove/recreate (avoids auth blips and "policy in use").
# Do not add `policy remove` / `user remove` here unless the pin's behavior changes.
set -eu

: "${MINIO_ROOT_USER:?MINIO_ROOT_USER required}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD required}"
: "${MINIO_LOADER_USER:?MINIO_LOADER_USER required}"
: "${MINIO_LOADER_PASSWORD:?MINIO_LOADER_PASSWORD required}"
: "${MINIO_READER_USER:?MINIO_READER_USER required}"
: "${MINIO_READER_PASSWORD:?MINIO_READER_PASSWORD required}"
: "${MINIO_PLATFORM_READER_USER:?MINIO_PLATFORM_READER_USER required}"
: "${MINIO_PLATFORM_READER_PASSWORD:?MINIO_PLATFORM_READER_PASSWORD required}"
: "${MINIO_ADMIN_USER:?MINIO_ADMIN_USER required}"
: "${MINIO_ADMIN_PASSWORD:?MINIO_ADMIN_PASSWORD required}"

mc alias set nexus "http://minio:9000" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null

apply_policy() {
  name="$1"
  file="$2"
  mc admin policy create nexus "${name}" "${file}" >/dev/null
}

ensure_user() {
  user="$1"
  password="$2"
  policy="$3"
  mc admin user add nexus "${user}" "${password}" >/dev/null
  mc admin policy attach nexus "${policy}" --user "${user}" >/dev/null
}

apply_policy nexus-loader /policies/nexus-loader.json
apply_policy nexus-reader /policies/nexus-reader.json
apply_policy nexus-platform-reader /policies/nexus-platform-reader.json
apply_policy nexus-admin /policies/nexus-admin.json

ensure_user "${MINIO_LOADER_USER}" "${MINIO_LOADER_PASSWORD}" nexus-loader
ensure_user "${MINIO_READER_USER}" "${MINIO_READER_PASSWORD}" nexus-reader
ensure_user "${MINIO_PLATFORM_READER_USER}" "${MINIO_PLATFORM_READER_PASSWORD}" nexus-platform-reader
ensure_user "${MINIO_ADMIN_USER}" "${MINIO_ADMIN_PASSWORD}" nexus-admin

echo "MinIO IAM users applied (nexus_loader, nexus_reader, nexus_platform_reader, nexus_admin)."
