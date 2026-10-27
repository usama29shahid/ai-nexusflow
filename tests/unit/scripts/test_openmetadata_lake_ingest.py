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
    assert "route_clickhouse_categories" in includes
    assert "route_clickhouse_brands" in includes
    assert "route_clickhouse_subcategories" in includes


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
    for name in (
        "raw_route__categories",
        "stg_route__categories",
        "dim_category",
        "raw_route__brands",
        "stg_route__brands",
        "dim_brand",
        "raw_route__subcategories",
        "stg_route__subcategories",
        "dim_subcategory",
    ):
        assert name in mod.REQUIRED_TABLES


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


def test_ordered_governance_terms_parents_before_descendants():
    mod = _load()
    doc = {
        "glossary": {"name": "Route"},
        "terms": [
            {"name": "Leaf", "parent": "Subcategory", "description": "x"},
            {"name": "Subcategory", "parent": "Category", "description": "x"},
            {"name": "Category", "description": "x"},
            {"name": "Product", "description": "x"},
        ],
    }
    assert [term["name"] for term in mod.ordered_governance_terms(doc)] == [
        "Category",
        "Product",
        "Subcategory",
        "Leaf",
    ]


def test_route_governance_terms_relations_and_assets():
    mod = _load()
    doc = mod.load_route_governance()
    assert doc["glossary"]["name"] == "Route"
    bodies = mod.build_term_bodies(doc)
    assert [body["name"] for body in bodies] == [
        "Product",
        "Category",
        "Brand",
        "ProductImage",
        "ProductSubcategoryMembership",
        "Subcategory",
    ]
    sub = next(body for body in bodies if body["name"] == "Subcategory")
    assert sub["parent"] == "Route.Category"
    sub_metric = next(body for body in mod.build_metric_bodies(doc) if body["name"] == "subcategory_count")
    assert sub_metric["tags"][0]["tagFQN"] == "Route.Category.Subcategory"
    pairs = mod.governance_relation_pairs(doc)
    assert ("Brand", "Product") in pairs
    assert ("Category", "Product") in pairs
    assert ("Product", "Subcategory") in pairs
    assert ("Product", "ProductImage") in pairs
    assert ("Product", "ProductSubcategoryMembership") in pairs
    assert ("ProductSubcategoryMembership", "Subcategory") in pairs
    assert len(pairs) == 6
    assets = mod.governance_asset_refs(doc, "dev")
    table_names = {asset["name"] for asset in assets if asset["entity"] == "table"}
    assert set(mod.REQUIRED_TABLES) <= table_names
    pipelines = {asset["name"] for asset in assets if asset["entity"] == "pipeline"}
    assert pipelines == {
        "route_clickhouse_products",
        "route_clickhouse_categories",
        "route_clickhouse_brands",
        "route_clickhouse_subcategories",
    }
    image = next(asset for asset in assets if asset["name"] == "brg_product_image")
    assert image["fqn"] == "nexus_clickhouse.default.gold_dev.brg_product_image"
    assert image["term_fqn"] == "Route.ProductImage"


def test_route_governance_metrics_match_cube_measures():
    import yaml

    mod = _load()
    doc = mod.load_route_governance()
    metrics = {metric["name"]: metric["description"] for metric in doc["metrics"]}
    bodies = mod.build_metric_bodies(doc)
    assert {body["name"] for body in bodies} == set(metrics)
    product = next(body for body in bodies if body["name"] == "product_count")
    assert product["metricExpression"] == {
        "language": "SQL",
        "code": "count(*) where is_active = 1",
    }
    assert product["tags"][0]["tagFQN"] == "Route.Product"
    assert product["tags"][0]["source"] == "Glossary"
    avg_price = next(body for body in bodies if body["name"] == "avg_price")
    assert avg_price["customUnitOfMeasurement"] == "price"

    cube_measures: dict[str, str] = {}
    for path in sorted(mod.CUBE_MODEL_DIR.glob("*.yml")):
        model = yaml.safe_load(path.read_text(encoding="utf-8"))
        for cube in model.get("cubes") or []:
            for measure in cube.get("measures") or []:
                name = measure["name"]
                cube_measures[name] = measure["description"].strip()
                filter_sql = " ".join(
                    item.get("sql", "") for item in (measure.get("filters") or [])
                )
                if name.endswith("_deleted_count"):
                    assert "is_deleted = 1" in filter_sql, name
                elif name.endswith("_version_count"):
                    assert "is_active" not in filter_sql, name
                else:
                    assert "is_active = 1" in filter_sql, name
    assert cube_measures == {name: text.strip() for name, text in metrics.items()}


def test_governance_assets_add_body_disables_dry_run():
    mod = _load()
    body = mod.governance_assets_add_body("asset-1", "table")
    assert body == {
        "dryRun": False,
        "assets": [{"id": "asset-1", "type": "table"}],
    }


def test_with_owner_sets_admin_user_ref():
    mod = _load()
    owned = mod.with_owner({"name": "Route"}, "user-1")
    assert owned["owners"] == [{"id": "user-1", "type": "user"}]
    assert owned["name"] == "Route"


def test_governance_owner_id_uses_logged_in_user():
    mod = _load()

    def fake_get(_jwt: str, path: str):
        assert path == "/api/v1/users/loggedInUser"
        return {"id": "uid-logged-in", "email": "platform@example.com"}

    mod._om_get = fake_get  # type: ignore[method-assign]
    assert mod.governance_owner_id("tok") == "uid-logged-in"


def test_governance_asset_target_skips_missing_pipeline():
    mod = _load()

    def missing(_jwt: str, path: str):
        raise RuntimeError(f"HTTP 404 {path}: not found")

    mod._om_get = missing  # type: ignore[method-assign]
    assert (
        mod._governance_asset_target(
            "tok",
            {
                "entity": "pipeline",
                "fqn": "nexus_airflow.route_clickhouse_products",
            },
        )
        is None
    )


def test_governance_asset_target_requires_table():
    mod = _load()

    def missing(_jwt: str, path: str):
        raise RuntimeError(f"HTTP 404 {path}: not found")

    mod._om_get = missing  # type: ignore[method-assign]
    try:
        mod._governance_asset_target(
            "tok",
            {
                "entity": "table",
                "fqn": "nexus_clickhouse.default.gold_dev.dim_product",
            },
        )
    except RuntimeError as exc:
        assert "Governance asset missing" in str(exc)
    else:
        raise AssertionError("expected missing table to raise")


def test_cube_scd2_dimensions_are_not_primary_keys():
    import yaml

    mod = _load()
    for path in sorted(mod.CUBE_MODEL_DIR.glob("*.yml")):
        model = yaml.safe_load(path.read_text(encoding="utf-8"))
        for cube in model.get("cubes") or []:
            for dim in cube.get("dimensions") or []:
                assert not dim.get("primary_key"), (
                    f"{path.name}:{cube['name']}.{dim['name']} must not be "
                    "primary_key over multi-version SCD2 SQL"
                )
