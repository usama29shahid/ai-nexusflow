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
ENV UV_PROJECT_ENVIRONMENT=/opt/nexus/.venv
ENV PATH="/opt/nexus/.venv/bin:${PATH}"
ENV PYTHONPATH=/workspace
WORKDIR /workspace

CMD ["bash", "-lc", "echo 'nexus-elt: pass a command (Airflow docker run)' >&2; exit 2"]
