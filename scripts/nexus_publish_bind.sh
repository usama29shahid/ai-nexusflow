# Resolve NEXUS_PUBLISH_BIND for local vs vps, fail-closed on public binds in vps mode.
# Sourced by ./scripts/start.sh (before compose up). Unit tests source this file directly.
#
# Usage:
#   # shellcheck source=scripts/nexus_publish_bind.sh
#   source "${ROOT}/scripts/nexus_publish_bind.sh"
#   nexus_resolve_publish_bind || exit 1
#
# Expects NEXUS_EDGE_MODE (default local). Sets/export NEXUS_PUBLISH_BIND.
# Returns 1 on vps + 0.0.0.0 / :: / [::].

nexus_resolve_publish_bind() {
  local mode="${NEXUS_EDGE_MODE:-local}"
  # Compose default is 127.0.0.1 (VPS-safe even for raw `docker compose`).
  # Local start.sh opens 0.0.0.0 unless overridden; never set 0.0.0.0 on a VPS.
  if [[ "${mode}" == "vps" ]]; then
    export NEXUS_PUBLISH_BIND="${NEXUS_PUBLISH_BIND:-127.0.0.1}"
    case "${NEXUS_PUBLISH_BIND}" in
      0.0.0.0 | :: | "[::]")
        echo "start.sh: fatal: NEXUS_EDGE_MODE=vps cannot use NEXUS_PUBLISH_BIND=${NEXUS_PUBLISH_BIND}" >&2
        echo "start.sh: set NEXUS_PUBLISH_BIND=127.0.0.1 (or omit) so backends are not internet-facing" >&2
        return 1
        ;;
    esac
  else
    export NEXUS_PUBLISH_BIND="${NEXUS_PUBLISH_BIND:-0.0.0.0}"
  fi
  return 0
}
