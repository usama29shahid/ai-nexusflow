"""OpenMetadata reader ingest — lake/warehouse → OM catalog (not a product ELT DAG)."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

from nexus_elt_exec import elt_openmetadata_ingest_command

with DAG(
    dag_id="observability_openmetadata_ingest",
    description=(
        "Project ClickHouse + lake dbt/Airflow signals into OpenMetadata "
        "(reader; does not run dlt/dbt)"
    ),
    start_date=datetime(2024, 1, 1),
    # Daily reader refresh; fails if OpenMetadata profile is down. Manual trigger anytime.
    schedule=timedelta(days=1),
    catchup=False,
    max_active_runs=1,
    tags=["observability", "openmetadata", "reader"],
    params={
        "force": Param(
            False,
            type="boolean",
            description=(
                "Re-ingest even when a lake marker exists for the latest dbt run_id. "
                "Also accepted via trigger conf: {\"force\": true}."
            ),
        ),
    },
) as dag:
    BashOperator(
        task_id="openmetadata_ingest",
        bash_command=elt_openmetadata_ingest_command(),
    )
