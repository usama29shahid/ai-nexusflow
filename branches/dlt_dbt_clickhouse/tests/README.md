# tests — dlt_dbt_clickhouse

Mirror production layout. Python tests under `dlt/`; dbt singular/custom under `dbt/`.

```text
tests/
  dlt/{source}/unit/          # Python unittest (mirrors dlt/{source}/)
  dlt/{source}/regression/    # later
  dbt/{staging|gold|…}/       # dbt test-paths only (mirrors models/)
```

Generic dbt data tests stay in `models/**/schema.yml` (not Python unit tests).

```bash
# from repo root
uv run python branches/dlt_dbt_clickhouse/tests/dlt/route/unit/test_products_guards.py
```

Shared SDK tests: repo `tests/unit/common/`. Compose smokes: repo `tests/integration/`.
