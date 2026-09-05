"""Post-run observability publish helpers for dlt/dbt CLI entrypoints."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from common.observability.lake import copy_dbt_artifacts, publish_pipeline_event, publish_run_summary
from common.observability.otel import record_dlt_load


_BRANCH_BY_PROJECT = {
    "dlt_dbt_clickhouse": "dlt_dbt_clickhouse",
    "dlt_dbt_spark_iceberg": "dlt_dbt_spark_iceberg",
}


def branch_for_project_dir(project_dir: Path) -> str | None:
    return _BRANCH_BY_PROJECT.get(project_dir.name)


def publish_dlt_load(
    *,
    branch: str,
    component: str,
    pipeline_name: str,
    status: str = "ok",
    run_id: str | None = None,
    **extra: object,
) -> str:
    """Lake summary + pipeline event + best-effort OTLP span/metric after a dlt load."""
    rid = run_id or os.environ.get("NEXUS_RUN_ID", "local-unknown")
    event_type = "dlt.load.completed" if status == "ok" else "dlt.load.failed"
    attributes = {
        "pipeline_name": pipeline_name,
        "status": status,
        **{k: v for k, v in extra.items() if v is not None},
    }
    publish_pipeline_event(
        rid,
        branch=branch,
        component=component,
        event_type=event_type,
        attributes=attributes,
    )
    row_count = attributes.get("row_count", 0)
    try:
        row_count_int = int(row_count) if row_count is not None else 0
    except (TypeError, ValueError):
        row_count_int = 0
    record_dlt_load(
        run_id=rid,
        branch=branch,
        component=component,
        pipeline_name=pipeline_name,
        status=status,
        event_type=event_type,
        row_count=row_count_int,
        source=str(attributes["source"]) if attributes.get("source") is not None else None,
        endpoint=(
            str(attributes["endpoint"]) if attributes.get("endpoint") is not None else None
        ),
    )
    return publish_run_summary(
        rid,
        branch=branch,
        component=component,
        status=status,
        extra={
            "pipeline_name": pipeline_name,
            "phase": "dlt",
            "row_count": row_count_int,
        },
    )


def publish_dbt_run(
    project_dir: Path,
    *,
    status: str = "ok",
    run_id: str | None = None,
) -> tuple[list[str], str | None]:
    """Copy dbt artifacts to the lake and write run summary."""
    branch = branch_for_project_dir(project_dir.resolve())
    if branch is None:
        return [], None

    rid = run_id or os.environ.get("NEXUS_RUN_ID", "local-unknown")
    target = project_dir / "target"
    uploaded = copy_dbt_artifacts(branch, rid, target)
    event_type = "dbt.run.completed" if status == "ok" else "dbt.run.failed"
    publish_pipeline_event(
        rid,
        branch=branch,
        component="dbt",
        event_type=event_type,
        attributes={"status": status, "artifact_count": len(uploaded)},
    )
    summary_uri = publish_run_summary(
        rid,
        branch=branch,
        component="dbt",
        status=status,
        extra={"artifact_count": len(uploaded), "phase": "dbt"},
    )
    return uploaded, summary_uri


def _project_dir_from_dbt_argv(argv: list[str]) -> Path | None:
    args = argv[1:] if argv and argv[0].endswith(".py") else argv
    for index, arg in enumerate(args):
        if arg == "--project-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if arg.startswith("--project-dir="):
            return Path(arg.split("=", 1)[1])
    return None


def resolve_dbt_project_dir(argv: list[str] | None = None) -> Path | None:
    """Resolve dbt project dir from NEXUS_DBT_PROJECT_DIR or dbt CLI argv."""
    env_dir = os.environ.get("NEXUS_DBT_PROJECT_DIR")
    if env_dir:
        path = Path(env_dir)
        if path.is_dir():
            return path.resolve()

    if argv is not None:
        from_argv = _project_dir_from_dbt_argv(argv)
        if from_argv is not None and from_argv.is_dir():
            return from_argv.resolve()

    return None


def after_dbt_cli(argv: list[str] | None = None, *, exit_code: int = 0) -> None:
    """Best-effort lake publish after `dbt` CLI (called from start.sh)."""
    args = argv if argv is not None else sys.argv
    project_dir = resolve_dbt_project_dir(args)
    if project_dir is None:
        return

    status = "ok" if exit_code == 0 else "failed"
    uploaded, summary_uri = publish_dbt_run(project_dir, status=status)
    if summary_uri:
        print(f"Observability lake: {summary_uri}")
    for uri in uploaded:
        print(f"Observability lake: {uri}")


if __name__ == "__main__":
    after_dbt_cli(exit_code=int(os.environ.get("NEXUS_DBT_EXIT_CODE", "0")))
