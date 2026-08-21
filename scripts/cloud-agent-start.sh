#!/usr/bin/env bash
# Per-boot startup: Docker daemon + Compose infrastructure stacks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run cloud-agent-install.sh first." >&2
  exit 1
fi

ensure_docker() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  sudo update-alternatives --set iptables /usr/sbin/iptables-legacy 2>/dev/null || true
  sudo update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy 2>/dev/null || true

  if ! pgrep -x dockerd >/dev/null 2>&1; then
    echo "Starting Docker daemon..."
    sudo dockerd --host=unix:///var/run/docker.sock >/tmp/dockerd.log 2>&1 &
  fi

  for _ in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Docker daemon did not become ready." >&2
  tail -20 /tmp/dockerd.log >&2 || true
  exit 1
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-60}"

  for _ in $(seq 1 "$attempts"); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "${label} ready."
      return 0
    fi
    sleep 2
  done

  echo "${label} did not become ready (${url})." >&2
  return 1
}

ensure_docker

set -a
# shellcheck source=/dev/null
source .env
set +a
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-clickhouse,lakehouse}"

echo "Starting infrastructure (COMPOSE_PROFILES=${COMPOSE_PROFILES})..."
docker compose up -d

wait_for_http "http://localhost:8123/ping" "ClickHouse"
wait_for_http "http://localhost:9002/minio/health/live" "MinIO"

if [[ "${COMPOSE_PROFILES}" == *"lakehouse"* ]]; then
  wait_for_http "http://localhost:8182/q/health" "Polaris" 90
  wait_for_http "http://localhost:8080/v1/info" "Trino" 90
  for _ in $(seq 1 90); do
    if bash -c 'cat < /dev/null > /dev/tcp/localhost/10000' 2>/dev/null; then
      echo "Spark Thrift ready."
      break
    fi
    sleep 3
  done
fi

echo "Infrastructure startup complete."
