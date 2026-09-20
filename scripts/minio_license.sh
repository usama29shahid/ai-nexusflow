# Guard the AIStor Free license file before Compose bind-mounts it.
# Sourced by ./scripts/start.sh and ./scripts/setup.sh. Unit tests source this file directly.
#
# Usage:
#   # shellcheck source=scripts/minio_license.sh
#   source "${ROOT}/scripts/minio_license.sh"
#   require_minio_license || exit 1
#
# Expects ROOT (repo root). Honors MINIO_LICENSE_FILE when set.
# Returns 1 if the path is missing or is a directory (Docker creates a directory
# when a bind-mounted file does not exist).

require_minio_license() {
  local license="${MINIO_LICENSE_FILE:-${ROOT}/.nexusflow/minio.license}"
  if [[ -d "${license}" ]]; then
    echo "MinIO AIStor license path is a directory: ${license}" >&2
    echo "Docker Compose creates that directory when the file is missing on first up." >&2
    echo "Remove it (rmdir '${license}'), then copy the license file. See docker/minio/README.md." >&2
    return 1
  fi
  if [[ ! -f "${license}" ]]; then
    echo "Missing MinIO AIStor license: ${license}" >&2
    echo "Copy the Free license to .nexusflow/minio.license (chmod 600) before ./scripts/setup.sh or ./scripts/start.sh." >&2
    echo "Bare docker compose up does not check this. See docker/minio/README.md." >&2
    return 1
  fi
  return 0
}
