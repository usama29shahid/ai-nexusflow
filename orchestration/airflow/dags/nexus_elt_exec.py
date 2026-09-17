"""Airflow helper: run ELT tasks in the ephemeral nexus-elt container. Not a DAG."""

from __future__ import annotations

import shlex


def elt_bash_command(remote: str) -> str:
    """BashOperator command: ``docker run`` nexus-elt with the given remote argv.

    ``remote`` is a shell fragment run under ``bash -lc`` inside the job container
    (repo at ``/workspace``). It may contain Airflow Jinja (``{{ run_id }}``).

    Do not wrap with ``./scripts/start.sh`` — that script starts Compose/Vault.
    Pass secrets via ``--env-file`` from ``airflow_elt.env`` (written on the host by
    ``./scripts/start.sh airflow``). Override warehouse hosts to Compose DNS.

    Password rotation: re-run ``./scripts/start.sh airflow`` on the host (Vault Agent
    ``secrets.env`` is not mounted into the scheduler — keeps vault-init / AppRole
    off the docker.sock container).

    Caveat: ``-e NEXUS_RUN_ID='{{ run_id }}'`` (and DAG/task id) use shell single
    quotes. Airflow's default ``run_id`` charset is safe; do not pass a custom
    run id containing ``'``. The ``remote`` fragment is protected with
    ``shlex.quote``.
    """
    # Host path for -v must be the Docker *host* path (daemon is on the host).
    # shlex.quote keeps the remote fragment one safe argv for bash -lc (including
    # selectors / run-ids that contain single quotes). Jinja still expands
    # {{ run_id }} etc. on the full bash_command before the scheduler runs it.
    # The -e NEXUS_*='{{ … }}' lines below are NOT shlex-quoted — keep run_id
    # free of single quotes (see AGENTS.md orchestration notes).
    return (
        "set -euo pipefail\n"
        'image="${NEXUS_ELT_IMAGE:-nexus-elt:latest}"\n'
        'network="${NEXUS_COMPOSE_NETWORK:-ai-nexusflow_default}"\n'
        'repo="${NEXUS_REPO_ROOT:?Set NEXUS_REPO_ROOT to the host clone path}"\n'
        'envfile="${NEXUS_AIRFLOW_ELT_ENV_PATH:-/opt/airflow/nexus_elt.env}"\n'
        'if [[ ! -f "${envfile}" ]]; then\n'
        '  echo "Missing ELT env file (${envfile}). Run ./scripts/start.sh airflow" >&2\n'
        "  exit 1\n"
        "fi\n"
        'if [[ ! -r "${envfile}" ]]; then\n'
        '  echo "ELT env file not readable (${envfile}) by uid $(id -u)" >&2\n'
        "  exit 1\n"
        "fi\n"
        "docker run --rm \\\n"
        '  --network "${network}" \\\n'
        '  -v "${repo}:/workspace:rw" \\\n'
        "  -w /workspace \\\n"
        '  --env-file "${envfile}" \\\n'
        "  -e CLICKHOUSE_HOST=clickhouse \\\n"
        "  -e MINIO_ENDPOINT_URL=http://minio:9000 \\\n"
        "  -e AWS_ENDPOINT_URL=http://minio:9000 \\\n"
        "  -e OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 \\\n"
        "  -e NEXUS_ELT_JOB=1 \\\n"
        "  -e NEXUS_RUN_ID='{{ run_id }}' \\\n"
        "  -e NEXUS_DAG_ID='{{ dag.dag_id }}' \\\n"
        "  -e NEXUS_TASK_ID='{{ task.task_id }}' \\\n"
        "  -e PYTHONPATH=/workspace \\\n"
        "  -e UV_PROJECT_ENVIRONMENT=/opt/nexus/.venv \\\n"
        '  "${image}" \\\n'
        f"  bash -lc {shlex.quote(remote)}\n"
    )


def elt_dbt_layer(select: str) -> str:
    """``dbt run`` then ``dbt test`` for one selector. Never ``dbt build``."""
    return elt_bash_command(f"./scripts/airflow-dbt-layer.sh {shlex.quote(select)}")
