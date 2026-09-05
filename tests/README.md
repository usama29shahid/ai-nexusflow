# tests

Integration tests run on the host against Compose services (`uv run`). Not inside Docker.

## Unit

Branch-owned (mirrors `dlt/{source}/`):

```bash
uv run python branches/dlt_dbt_clickhouse/tests/dlt/route/unit/test_products_guards.py
```

Shared `common/` SDK:

```bash
uv run python tests/unit/common/test_observability_publish.py
uv run python tests/unit/common/test_observability_otel.py
```
