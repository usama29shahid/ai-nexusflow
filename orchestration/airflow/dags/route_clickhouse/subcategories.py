"""Route subcategories → ClickHouse: one DAG per source + target + endpoint.

Silver tests ``category_id`` against ``stg_route__categories``. Categories must
finish first, so this DAG triggers ``route_clickhouse_categories`` and waits
before its own Bronze load. Unpause that DAG or the trigger fails.
"""

from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG
from airflow.utils.trigger_rule import TriggerRule

from nexus_elt_exec import elt_bash_command, elt_dbt_layer

with DAG(
    dag_id="route_clickhouse_subcategories",
    description="Route /subcategories after categories: Bronze + silver + gold + observability",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    # trigger_categories waits in-process (no triggerer) and holds a worker
    # until categories finishes. One active run leaves the other workers free.
    max_active_runs=1,
    tags=["route", "clickhouse", "subcategories"],
) as dag:
    assert_branch_enabled = BashOperator(
        task_id="assert_branch_enabled",
        bash_command=elt_bash_command(
            "./scripts/assert-branch-enabled.sh dlt_dbt_clickhouse"
        ),
    )
    # Refresh categories silver before the subcategory relationship test.
    # deferrable stays off: this Compose file has no triggerer.
    trigger_categories = TriggerDagRunOperator(
        task_id="trigger_categories",
        trigger_dag_id="route_clickhouse_categories",
        wait_for_completion=True,
        poke_interval=30,
        allowed_states=["success"],
        failed_states=["failed"],
        fail_when_dag_is_paused=True,
        deferrable=False,
    )
    bronze = BashOperator(
        task_id="bronze",
        bash_command=elt_bash_command(
            "uv run python branches/dlt_dbt_clickhouse/dlt/route/subcategories.py "
            "--run-id '{{ run_id }}'"
        ),
    )
    silver = BashOperator(
        task_id="silver",
        bash_command=elt_dbt_layer("tag:subcategories,tag:staging"),
    )
    gold = BashOperator(
        task_id="gold",
        bash_command=elt_dbt_layer("tag:subcategories,tag:gold"),
    )
    observability = BashOperator(
        task_id="observability",
        bash_command=elt_bash_command("./scripts/observability-publish-run.sh"),
    )
    observability_failed = BashOperator(
        task_id="observability_failed",
        trigger_rule=TriggerRule.ONE_FAILED,
        bash_command=elt_bash_command(
            "./scripts/observability-publish-run.sh failed"
        ),
    )

    (
        assert_branch_enabled
        >> trigger_categories
        >> bronze
        >> silver
        >> gold
        >> observability
    )
    [
        assert_branch_enabled,
        trigger_categories,
        bronze,
        silver,
        gold,
        observability,
    ] >> observability_failed
