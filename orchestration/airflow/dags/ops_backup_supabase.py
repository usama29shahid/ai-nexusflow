"""Daily Supabase Postgres → R2 (logical dump). Not a product ELT DAG."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

from nexus_elt_exec import elt_backup_supabase_command

with DAG(
    dag_id="ops_backup_supabase",
    description=(
        "pg_dump supabase-db to MinIO "
        "(nexus-supabase-{env}/dumps/YYYY/MM/DD/). "
        "R2 mirror is ops_backup_archive. Requires MinIO + supabase-db."
    ),
    start_date=datetime(2024, 1, 1),
    schedule=timedelta(days=1),
    catchup=False,
    max_active_runs=1,
    tags=["ops", "backup", "supabase", "minio"],
) as dag:
    BashOperator(
        task_id="backup_supabase",
        bash_command=elt_backup_supabase_command(),
    )
