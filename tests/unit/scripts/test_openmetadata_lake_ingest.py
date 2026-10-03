"""Unit tests for scripts/openmetadata_lake_ingest.py (no Docker / MinIO)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "openmetadata_lake_ingest.py"


def _load():
    spec = importlib.util.spec_from_file_location("om_lake", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["om_lake"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_layer_databases():
    mod = _load()
    assert mod.layer_databases("dev") == [
        "bronze_dev",
        "silver_dev",
        "gold_dev",
        "elementary_dev",
    ]


def test_marker_key():
    mod = _load()
    key = mod.marker_key("local-2026-09-27T12:00:00Z")
    assert key.startswith("indexes/openmetadata/")
    assert "dlt_dbt_clickhouse" in key
    assert key.endswith(".ingested")


def test_build_clickhouse_workflow_filters_and_no_mark_delete():
    mod = _load()
    wf = mod.build_clickhouse_workflow(
        jwt_token="tok",
        username="nexus_catalog",
        password="secret",
        host_port="clickhouse:8123",
        databases=["bronze_dev", "silver_dev", "gold_dev", "elementary_dev"],
        om_host_port="http://openmetadata-server:8585/api",
    )
    assert wf["source"]["type"] == "clickhouse"
    assert wf["source"]["serviceName"] == "nexus_clickhouse"
    cfg = wf["source"]["serviceConnection"]["config"]
    assert cfg["username"] == "nexus_catalog"
    assert cfg["scheme"] == "clickhouse+http"
    assert cfg["hostPort"] == "clickhouse:8123"
    src = wf["source"]["sourceConfig"]["config"]
    assert src["markDeletedTables"] is False
    assert src["markDeletedSchemas"] is False
    assert src["schemaFilterPattern"]["includes"] == [
        "bronze_dev",
        "silver_dev",
        "gold_dev",
        "elementary_dev",
    ]
    assert wf["workflowConfig"]["openMetadataServerConfig"]["storeServiceConnection"] is False
    assert (
        wf["workflowConfig"]["openMetadataServerConfig"]["securityConfig"]["jwtToken"]
        == "tok"
    )


def test_build_dbt_workflow_local_paths():
    mod = _load()
    wf = mod.build_dbt_workflow(
        jwt_token="tok",
        om_host_port="http://openmetadata-server:8585/api",
        manifest_path="/dbt/manifest.json",
        catalog_path="/dbt/catalog.json",
        run_results_path="/dbt/run_results.json",
        sources_path="/dbt/sources.json",
    )
    assert wf["source"]["type"] == "dbt"
    assert wf["source"]["serviceName"] == "nexus_clickhouse"
    cfg = wf["source"]["sourceConfig"]["config"]
    assert cfg["searchAcrossDatabases"] is True
    assert cfg["overrideLineage"] is True
    dbt = cfg["dbtConfigSource"]
    assert dbt["dbtConfigType"] == "local"
    assert dbt["dbtManifestFilePath"] == "/dbt/manifest.json"
    assert dbt["dbtCatalogFilePath"] == "/dbt/catalog.json"
    assert dbt["dbtSourcesFilePath"] == "/dbt/sources.json"


def test_build_clickhouse_profiler_workflow():
    mod = _load()
    wf = mod.build_clickhouse_profiler_workflow(
        jwt_token="tok",
        username="nexus_catalog",
        password="secret",
        host_port="clickhouse:8123",
        databases=["bronze_dev", "silver_dev", "gold_dev", "elementary_dev"],
        om_host_port="http://openmetadata-server:8585/api",
    )
    assert wf["source"]["type"] == "clickhouse"
    assert wf["source"]["serviceName"] == "nexus_clickhouse"
    assert "serviceConnection" in wf["source"]
    cfg = wf["source"]["sourceConfig"]["config"]
    assert cfg["type"] == "Profiler"
    assert cfg["computeTableMetrics"] is True
    assert cfg["computeColumnMetrics"] is True
    assert "generateSampleData" not in cfg
    assert cfg["databaseFilterPattern"]["includes"] == ["default"]
    assert cfg["schemaFilterPattern"]["includes"] == [
        "bronze_dev",
        "silver_dev",
        "gold_dev",
        "elementary_dev",
    ]
    assert wf["processor"]["type"] == "orm-profiler"
    assert wf["sink"]["type"] == "metadata-rest"
    assert (
        wf["workflowConfig"]["openMetadataServerConfig"]["storeServiceConnection"]
        is False
    )


def test_build_airflow_workflow_postgres_backend():
    mod = _load()
    wf = mod.build_airflow_workflow(
        jwt_token="tok",
        om_host_port="http://openmetadata-server:8585/api",
    )
    assert wf["source"]["type"] == "airflow"
    assert wf["source"]["serviceName"] == "nexus_airflow"
    conn = wf["source"]["serviceConnection"]["config"]["connection"]
    assert conn["type"] == "Postgres"
    assert conn["hostPort"] == "airflow-postgres:5432"
    includes = wf["source"]["sourceConfig"]["config"]["pipelineFilterPattern"][
        "includes"
    ]
    assert "route_clickhouse_products" in includes


def test_rewrite_manifest_sources_for_om():
    import tempfile

    mod = _load()
    manifest = {
        "sources": {
            "source.nexus_clickhouse.route_raw.products": {
                "database": "bronze_dev",
                "schema": "bronze_dev",
                "identifier": "raw_route__products",
            }
        }
    }
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        assert mod.rewrite_manifest_sources_for_om(path) == 1
        data = json.loads(path.read_text(encoding="utf-8"))
        assert (
            data["sources"]["source.nexus_clickhouse.route_raw.products"]["database"]
            == "default"
        )
        assert (
            data["sources"]["source.nexus_clickhouse.route_raw.products"]["schema"]
            == "bronze_dev"
        )


def test_required_tables_include_products():
    mod = _load()
    assert "raw_route__products" in mod.REQUIRED_TABLES
    assert "stg_route__products" in mod.REQUIRED_TABLES
    assert "dim_product" in mod.REQUIRED_TABLES


def test_docker_host_path_rewrites_workspace_under_nexus_repo_root():
    import os

    mod = _load()
    prev = os.environ.get("NEXUS_REPO_ROOT")
    prev_root = mod.REPO_ROOT
    try:
        os.environ["NEXUS_REPO_ROOT"] = "/host/clone"
        # Simulate nexus-elt layout: REPO_ROOT is /workspace inside the job image.
        mod.REPO_ROOT = Path("/workspace")
        got = mod.docker_host_path(
            "/workspace/.nexusflow/openmetadata/clickhouse_metadata.yaml"
        )
        assert got == "/host/clone/.nexusflow/openmetadata/clickhouse_metadata.yaml"
        bind = mod.docker_volume_bind(
            "/workspace/.nexusflow/openmetadata", "/workflows", mode="ro"
        )
        assert bind == "/host/clone/.nexusflow/openmetadata:/workflows:ro"
    finally:
        mod.REPO_ROOT = prev_root
        if prev is None:
            os.environ.pop("NEXUS_REPO_ROOT", None)
        else:
            os.environ["NEXUS_REPO_ROOT"] = prev


def test_docker_host_path_noop_without_nexus_repo_root():
    import os
    import tempfile

    mod = _load()
    prev = os.environ.pop("NEXUS_REPO_ROOT", None)
    try:
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "wf.yaml"
            f.write_text("x: 1\n", encoding="utf-8")
            assert mod.docker_host_path(f) == str(f.resolve())
    finally:
        if prev is not None:
            os.environ["NEXUS_REPO_ROOT"] = prev


def test_write_dbt_success_marker_if_ok_skips_on_soft_fail():
    from unittest.mock import MagicMock

    mod = _load()
    client = MagicMock()
    assert (
        mod.write_dbt_success_marker_if_ok(
            client, "nexus-telemetry-dev", "run-1", dbt_ok=False
        )
        is False
    )
    client.put_object.assert_not_called()


def test_write_dbt_success_marker_if_ok_writes_on_success():
    from unittest.mock import MagicMock, patch

    mod = _load()
    client = MagicMock()
    # Prefer compose network off so write_marker uses boto client.put_object.
    with patch.object(mod, "prefer_compose_network", return_value=False):
        assert (
            mod.write_dbt_success_marker_if_ok(
                client, "nexus-telemetry-dev", "run-1", dbt_ok=True
            )
            is True
        )
    client.put_object.assert_called_once()
    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "nexus-telemetry-dev"
    assert kwargs["Key"].endswith("run-1.ingested")


def test_deep_dive_public_base_uses_caddy_hostnames():
    import os

    mod = _load()
    prev_host = os.environ.get("NEXUS_PUBLIC_HOST")
    prev_scheme = os.environ.get("NEXUS_CADDY_SITE_SCHEME")
    try:
        os.environ["NEXUS_PUBLIC_HOST"] = "localhost.com"
        os.environ["NEXUS_CADDY_SITE_SCHEME"] = "http://"
        assert (
            mod.deep_dive_public_base("elementary")
            == "http://elementary.localhost.com/"
        )
        assert mod.deep_dive_public_base("docs") == "http://docs.localhost.com/"
        assert (
            mod.deep_dive_public_base("openmetadata")
            == "http://openmetadata.localhost.com/"
        )
    finally:
        if prev_host is None:
            os.environ.pop("NEXUS_PUBLIC_HOST", None)
        else:
            os.environ["NEXUS_PUBLIC_HOST"] = prev_host
        if prev_scheme is None:
            os.environ.pop("NEXUS_CADDY_SITE_SCHEME", None)
        else:
            os.environ["NEXUS_CADDY_SITE_SCHEME"] = prev_scheme
