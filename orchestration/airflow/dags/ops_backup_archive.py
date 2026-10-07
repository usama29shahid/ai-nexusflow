"""Daily MinIO REST archive → R2 (secondary backup). Not a product ELT DAG."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

from nexus_elt_exec import elt_backup_archive_command

with DAG(
    dag_id="ops_backup_archive",
    description=(
        "Mirror MinIO REST archive buckets to Cloudflare R2 "
        "(same names/keys; no --remove). Requires Vault backup KV + MinIO up."
    ),
    start_date=datetime(2024, 1, 1),
    schedule=timedelta(days=1),
    catchup=False,
    max_active_runs=1,
    tags=["ops", "backup", "minio", "r2"],
) as dag:
    BashOperator(
        task_id="backup_archive",
        bash_command=elt_backup_archive_command(),
    )
