# Bronze → RBAC → silver (decision / implementation log)

**Status: implemented for Route products (dev verified).**  
**Purpose:** Implementation record and historical lock. Normative rules live in the docs below — do not duplicate full tables here.  
**Next:** Gold for products; categories/brands; optional DROP of legacy `warehouse.raw_route_*` tables.

| Topic | Canonical doc |
| --- | --- |
| Layer databases, env-on-DB-only, dlt separator `__` | [environments.md](environments.md) |
| Silver peer tables, `stg_` rules, YAML, packages, hashes | [dbt-modeling.md](dbt-modeling.md) |
| Warehouse CH layout, dlt physical names, products example | [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md) |
| Loader / transformer / reader / admin, Vault siblings | [rbac.md](rbac.md) |

Also: [observability.md](observability.md), [vault.md](vault.md).

---

## Implementation order (locked)

1. Docs + **ClickHouse RBAC** (users, GRANTs, Vault sibling secrets, env wiring)
2. **dlt** Bronze cutover as **`nexus_loader`** (`warehouse…___*` → `bronze_{env}.raw_*__*`)
3. **dbt** silver peer tables as **`nexus_transformer`**

Reason RBAC started with the rename: Bronze physical names and CH connection config changed in the same slice.

---

## Verify checklist

- [x] Users/GRANTs exist; Vault/env wired (`./scripts/clickhouse-rbac-bootstrap.sh`)
- [x] dlt as loader → `bronze_dev.raw_route__products` (+ nested tables)
- [x] Loader cannot create/write `silver_dev`
- [x] dbt as transformer builds three `stg_route__products*` tables + elementary
- [x] `dbt docs generate`; catalog.json written
- [x] Reader cannot INSERT bronze
- [x] dbt tests + unit test pass (products peer tables)

---

## Explicitly deferred

- Gold dims / SCD / incremental / soft-delete
- MinIO IAM policies
- OM / SigNoz / Elementary **UI** product setup
- Airflow source DAG, categories/brands endpoints
- Full Terraform modules + GitHub Actions workflows (naming/RBAC already compatible)
- `dlt_smoke` rename to new bronze pattern
