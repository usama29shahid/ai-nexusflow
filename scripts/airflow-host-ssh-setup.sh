#!/usr/bin/env bash
# One-time SSH key for Dockerized Airflow → Docker host (WSL or VPS).
# Writes a restricted authorized_keys line (command= wrapper, from= private nets).
# Does not start sshd. See orchestration/airflow/README.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY_DIR="${ROOT}/.nexusflow/airflow_ssh"
KEY_PATH="${KEY_DIR}/id_ed25519"
PUB_PATH="${KEY_PATH}.pub"
WRAPPER="${ROOT}/scripts/airflow-host-ssh-command.sh"
# Source IPs allowed to use this key. Override if host-gateway appears elsewhere.
FROM="${NEXUS_AIRFLOW_SSH_FROM:-127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"

chmod +x "${WRAPPER}"

mkdir -p "${KEY_DIR}"
chmod 700 "${KEY_DIR}"

if [[ ! -f "${KEY_PATH}" ]]; then
  ssh-keygen -t ed25519 -N "" -f "${KEY_PATH}" -C "nexus-airflow-host-exec"
  echo "Created ${KEY_PATH}"
else
  echo "Key already exists: ${KEY_PATH}"
fi
chmod 600 "${KEY_PATH}"
chmod 644 "${PUB_PATH}"

AUTH="${HOME}/.ssh/authorized_keys"
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

pub="$(cat "${PUB_PATH}")"
key_id="$(awk '{print $1 " " $2}' "${PUB_PATH}")"
auth_line="restrict,from=\"${FROM}\",command=\"${WRAPPER}\" ${pub}"

if [[ -f "${AUTH}" ]]; then
  grep -vF "${key_id}" "${AUTH}" > "${AUTH}.nexus.tmp" || true
  mv "${AUTH}.nexus.tmp" "${AUTH}"
fi
echo "${auth_line}" >> "${AUTH}"
chmod 600 "${AUTH}"
echo "Wrote restricted authorized_keys line (command=${WRAPPER})"

echo
echo "Host user for Compose: $(id -un)  (set NEXUS_HOST_USER in .env)"
echo "Repo root:             ${ROOT}  (set NEXUS_REPO_ROOT in .env)"
echo "SSH from=:             ${FROM}  (override NEXUS_AIRFLOW_SSH_FROM if tasks fail to connect)"
echo "Enable sshd if needed, then: ./scripts/start.sh airflow"
