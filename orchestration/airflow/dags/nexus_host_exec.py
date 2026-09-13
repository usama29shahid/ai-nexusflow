"""SSH helper so Dockerized Airflow runs host start.sh / uv. Not a DAG."""

from __future__ import annotations


def host_bash_command(remote: str) -> str:
    """BashOperator command: SSH to the Docker host and run start.sh.

    ``remote`` is appended after ``./scripts/start.sh``. It may contain Airflow
    Jinja (``{{ run_id }}``). ``NEXUS_REPO_ROOT`` expands in the container so
    the host ``cd`` uses the same path.
    """
    return (
        "set -euo pipefail\n"
        "ssh -4 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "
        "-o UserKnownHostsFile=/tmp/nexus_known_hosts "
        '-i "${NEXUS_AIRFLOW_SSH_KEY_PATH:-/opt/airflow/.ssh/id_ed25519}" '
        '-p "${NEXUS_HOST_PORT:-22}" '
        '"${NEXUS_HOST_USER:?Set NEXUS_HOST_USER}@${NEXUS_HOST:-host.docker.internal}" '
        "\"export NEXUS_RUN_ID='{{ run_id }}' "
        "NEXUS_DAG_ID='{{ dag.dag_id }}' "
        "NEXUS_TASK_ID='{{ task.task_id }}' "
        "OTEL_EXPORTER_OTLP_ENDPOINT=\\${OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4317}; "
        "cd '${NEXUS_REPO_ROOT:?Set NEXUS_REPO_ROOT}' && "
        f"./scripts/start.sh {remote}\""
    )


def host_dbt_layer(select: str) -> str:
    """``dbt run`` then ``dbt test`` for one selector. Never ``dbt build``."""
    return host_bash_command(f"./scripts/airflow-dbt-layer.sh '{select}'")