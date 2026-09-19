#!/usr/bin/env bash
# Manage /etc/hosts entries for Nexus edge subdomains under NEXUS_PUBLIC_HOST.
# *.localhost.com does NOT auto-resolve (unlike RFC *.localhost).
#
# Usage (from repo root):
#   ./scripts/proxy-hosts.sh install   # add block (needs sudo for /etc/hosts)
#   ./scripts/proxy-hosts.sh remove    # remove block (needs sudo for /etc/hosts)
#   ./scripts/proxy-hosts.sh print     # print lines for Windows hosts file
#
# Tests may set NEXUS_PROXY_HOSTS_FILE to a temp path (no sudo).
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Only these keys (never source the whole .env — avoids secrets + preserves caller overrides).
# Already-set environment variables win over .env. Optional: NEXUS_PROXY_DOTENV=/path/to/.env
DOTENV_FILE="${NEXUS_PROXY_DOTENV:-${ROOT}/.env}"

dotenv_value() {
  local key="$1"
  local file="$2"
  local line val
  [[ -f "${file}" ]] || return 0
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "${file}" | tail -n1 || true)"
  [[ -n "${line}" ]] || return 0
  line="${line#"${line%%[![:space:]]*}"}" # ltrim
  if [[ "${line}" == export[[:space:]]* ]]; then
    line="${line#export}"
    line="${line#"${line%%[![:space:]]*}"}"
  fi
  val="${line#"${key}="}"
  if [[ "${val}" == \"*\" ]]; then
    val="${val:1:${#val}-2}"
  elif [[ "${val}" == \'*\' ]]; then
    val="${val:1:${#val}-2}"
  fi
  printf '%s' "${val}"
}

if [[ -z "${NEXUS_PUBLIC_HOST:-}" ]]; then
  NEXUS_PUBLIC_HOST="$(dotenv_value NEXUS_PUBLIC_HOST "${DOTENV_FILE}")"
fi
if [[ -z "${NEXUS_PROXY_HOSTS_IP:-}" ]]; then
  NEXUS_PROXY_HOSTS_IP="$(dotenv_value NEXUS_PROXY_HOSTS_IP "${DOTENV_FILE}")"
fi

HOST="${NEXUS_PUBLIC_HOST:-localhost.com}"
IP="${NEXUS_PROXY_HOSTS_IP:-127.0.0.1}"
HOSTS_FILE="${NEXUS_PROXY_HOSTS_FILE:-/etc/hosts}"
MARKER_BEGIN="# nexus-edge-proxy BEGIN (${HOST})"
MARKER_END="# nexus-edge-proxy END (${HOST})"

SUBDOMAINS=(
  airflow
  minio
  cloudbeaver
  vault
  clickhouse
  polaris
  trino
  spark
  signoz
  openmetadata
  docs
  elementary
)

hosts_block() {
  echo "${MARKER_BEGIN}"
  for sub in "${SUBDOMAINS[@]}"; do
    echo "${IP} ${sub}.${HOST}"
  done
  echo "${MARKER_END}"
}

# Strip every complete Nexus edge-proxy block (any NEXUS_PUBLIC_HOST suffix).
# Abort if any BEGIN/END pair is incomplete — never truncate the rest of the file.
# VPS normally uses DNS A records instead of this script; when hosts *are* used
# (local WSL, or a temporary VPS hosts hack), install/remove stay domain-switch safe.
strip_nexus_blocks() {
  local src="$1"
  local dest="$2"
  if [[ ! -f "${src}" ]]; then
    : >"${dest}"
    return 0
  fi
  awk '
    /^# nexus-edge-proxy BEGIN \(/ {
      if (skip) {
        print "proxy-hosts: nested/duplicate BEGIN marker; refusing to rewrite hosts" > "/dev/stderr"
        exit 1
      }
      skip = 1
      next
    }
    /^# nexus-edge-proxy END \(/ {
      if (!skip) {
        print "proxy-hosts: END marker without BEGIN; refusing to rewrite hosts" > "/dev/stderr"
        exit 1
      }
      skip = 0
      next
    }
    !skip { print }
    END {
      if (skip) {
        print "proxy-hosts: BEGIN without matching END; refusing to rewrite hosts (would truncate the file)" > "/dev/stderr"
        exit 1
      }
    }
  ' "${src}" >"${dest}"
}

write_hosts_file() {
  local src="$1"
  if [[ "${HOSTS_FILE}" == "/etc/hosts" ]]; then
    sudo cp "${src}" "${HOSTS_FILE}"
  else
    cp "${src}" "${HOSTS_FILE}"
  fi
}

cmd="${1:-print}"
tmp=""
cleanup() {
  [[ -n "${tmp}" && -f "${tmp}" ]] && rm -f "${tmp}"
}
trap cleanup EXIT

case "${cmd}" in
  print)
    echo "Add these lines to /etc/hosts (Linux/WSL) and, if the browser is on Windows,"
    echo "to C:\\\\Windows\\\\System32\\\\drivers\\\\etc\\\\hosts :"
    echo
    echo "VPS: prefer DNS A records for *.${HOST} — do not rely on /etc/hosts in production."
    echo
    hosts_block
    ;;
  install)
    tmp="$(mktemp)"
    strip_nexus_blocks "${HOSTS_FILE}" "${tmp}"
    {
      echo
      hosts_block
    } >>"${tmp}"
    echo "Writing Nexus edge hosts for *.${HOST} → ${IP} (${HOSTS_FILE})..."
    echo "(Replaces any previous nexus-edge-proxy block, including an old NEXUS_PUBLIC_HOST.)"
    write_hosts_file "${tmp}"
    echo "Done. If you browse from Windows, also merge the same lines into the Windows hosts file:"
    echo "  ./scripts/proxy-hosts.sh print"
    ;;
  remove)
    tmp="$(mktemp)"
    strip_nexus_blocks "${HOSTS_FILE}" "${tmp}"
    echo "Removing all Nexus edge hosts blocks (${HOSTS_FILE})..."
    write_hosts_file "${tmp}"
    echo "Done."
    ;;
  *)
    echo "Usage: $0 {install|remove|print}" >&2
    exit 2
    ;;
esac
