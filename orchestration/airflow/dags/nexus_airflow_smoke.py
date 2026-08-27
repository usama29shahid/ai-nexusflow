"""Manual smoke DAG to verify the Airflow Compose profile.

Trigger from the UI after: docker compose --profile airflow up -d
Does not run dlt/dbt or touch branch pipelines.
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="nexus_airflow_smoke",
    description="NexusFlow Airflow smoke test (manual)",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["nexus", "smoke"],
) as dag:
    BashOperator(
        task_id="hello_nexus",
        bash_command=(
            'echo "nexus_airflow_smoke ok env=$${NEXUS_ENV:-dev} ts=$$(date -u +%Y-%m-%dT%H:%M:%SZ)"'
        ),
    )
