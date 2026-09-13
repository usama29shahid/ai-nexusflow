"""Route products → ClickHouse: one DAG per source + target + endpoint."""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule

from nexus_host_exec import host_bash_command, host_dbt_layer

with DAG(
    dag_id="route_clickhouse_products",
    description="Route /products dlt Bronze + silver + gold + observability",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["route", "clickhouse", "products"],
) as dag:
    assert_branch_enabled = BashOperator(
        task_id="assert_branch_enabled",
        bash_command=host_bash_command(
            "./scripts/assert-branch-enabled.sh dlt_dbt_clickhouse"
        ),
    )
    bronze = BashOperator(
        task_id="bronze",
        bash_command=host_bash_command(
            "uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py "
            "--run-id '{{ run_id }}'"
        ),
    )
    silver = BashOperator(
        task_id="silver",
        bash_command=host_dbt_layer("tag:products,tag:staging"),
    )
    gold = BashOperator(
        task_id="gold",
        bash_command=host_dbt_layer("tag:products,tag:gold"),
    )
    observability = BashOperator(
        task_id="observability",
        bash_command=host_bash_command("./scripts/observability-publish-run.sh"),
    )
    observability_failed = BashOperator(
        task_id="observability_failed",
        trigger_rule=TriggerRule.ONE_FAILED,
        bash_command=host_bash_command(
            "./scripts/observability-publish-run.sh failed"
        ),
    )

    assert_branch_enabled >> bronze >> silver >> gold >> observability
    [
        assert_branch_enabled,
        bronze,
        silver,
        gold,
        observability,
    ] >> observability_failed
