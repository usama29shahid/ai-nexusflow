# staging/route → silver_{env}

dbt silver (staging) for the Route API source. Peer tables over Bronze `bronze_{env}.raw_route__*` via `source()`.

**Implemented:** `stg_route__products`, `stg_route__products__images`, `stg_route__products__subcategory`, `stg_route__categories`, `stg_route__brands`, `stg_route__subcategories`.

- Config: `_route_sources.yml`, `_route_models.yml` (products peers), `_route_catalog_models.yml` (categories, brands, subcategories: tags, tests, and the subcategory `category_id` relationship to `stg_route__categories`)
- Materialization: table; FULL_LOAD lookback (`lookback_days`, default 15) / `--full-refresh` / optional `run_id`; dedupe by `pk_hash`
- Vars are **trusted** (validate at dlt/Airflow/operator): `run_id` matches dlt charset/length; `lookback_days` is a non-negative int. `--full-refresh` ignores both. Details: [docs/dbt-modeling.md](../../../../docs/dbt-modeling.md)
- ClickHouse user: `nexus_transformer` ([docs/rbac.md](../../../../docs/rbac.md))
- Record: [docs/bronze-silver-cutover.md](../../../../docs/bronze-silver-cutover.md)

Conformed Gold lives in shared `gold_{env}` / `marts_{env}`, not under this folder.
