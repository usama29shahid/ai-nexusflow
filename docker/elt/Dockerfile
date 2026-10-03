# syntax=docker/dockerfile:1
# Ephemeral ELT job image: dlt + dbt + elementary. Airflow starts one container per task.
# Host Cursor still uses uv on the laptop; this image is for orchestrated runs only.
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

WORKDIR /opt/nexus

# Lockfile layer first for cache. common/ is required for the hatchling package install.
COPY pyproject.toml uv.lock README.md ./
COPY common ./common

RUN uv sync --frozen --extra elementary \
    && uv run python -c "import dlt, dbt; print('elt deps ok')"

# Job mounts the repo at /workspace. Use the image venv — never the host .venv.
# Docker CLI: OpenMetadata reader DAG nests ``docker run`` for the OM ingestion image.
ARG TARGETARCH
ARG DOCKER_STATIC_VERSION=27.3.1
RUN case "${TARGETARCH}" in \
      amd64) DOCKER_ARCH=x86_64 ;; \
      arm64) DOCKER_ARCH=aarch64 ;; \
      *) echo "Unsupported TARGETARCH=${TARGETARCH:-unset}" >&2; exit 1 ;; \
    esac \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL \
      "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_STATIC_VERSION}.tgz" \
      | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && rm -rf /var/lib/apt/lists/* \
    && docker --version

ENV UV_PROJECT_ENVIRONMENT=/opt/nexus/.venv
ENV PATH="/opt/nexus/.venv/bin:${PATH}"
ENV PYTHONPATH=/workspace
WORKDIR /workspace

CMD ["bash", "-lc", "echo 'nexus-elt: pass a command (Airflow docker run)' >&2; exit 2"]
