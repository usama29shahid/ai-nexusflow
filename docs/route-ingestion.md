# Route API ingestion standard

This document is the source contract for ingesting [Route API](https://ecommerce.routemisr.com/) data through AI-NexusFlow capabilities.

It defines:

- Route endpoint meaning and data grain
- How this source maps to common dlt extraction rules
- Branch-specific archive, Bronze, and transformation naming
- Catalog-first vs authenticated entity sequencing

Route API is a **public educational/demo** ecommerce API. Treat its data as **synthetic/demo**, not production business data.

Pipelines are **not implemented yet**. This document orients naming and scope until the first Route dlt/dbt slice lands.

## Related standards

- [Architecture](architecture.md)
- [dlt extraction](dlt-extraction.md)
- [dlt_dbt_clickhouse](dlt-dbt-clickhouse.md)
- [dlt_dbt_spark_iceberg](dlt-dbt-spark-iceberg.md)
- [Environments](environments.md)
- [Observability](observability.md)
- [dbt modeling](dbt-modeling.md)
- [Enhanced modeling strategy](enhanced-modeling-strategy.md) — proposal only; do not change dlt/dbt process until accepted

Official / community references:

- [Route API site](https://ecommerce.routemisr.com/)
- Base URL: `https://ecommerce.routemisr.com`

## 1. Source contract

### API and inputs

| Item | Contract |
|---|---|
| API | Route ecommerce REST API |
| Base URL | `https://ecommerce.routemisr.com` |
| API prefix | `/api/v1` |
| Source id | `route` |
| Authentication (catalog) | None for public list/detail GETs |
| Authentication (user entities) | JWT after signup/signin — **deferred** until after catalog slice |
| Local environment | `NEXUS_ENV=dev` by default |
| Local run identity | A new shared `NEXUS_RUN_ID` for each load |

Credentials must never be hardcoded or committed. Catalog-only work needs no Vault path. JWT secrets for cart/orders/etc. are a later addition (see [vault.md](vault.md)).

### Endpoint, resource, job, and table

| Term | Meaning |
|---|---|
| Source | `route` — the external API |
| Endpoint | A Route REST contract, such as `GET /api/v1/products` |
| dlt resource | Extraction/load representation of one endpoint |
| Job | Executable dlt script or later Airflow task for that endpoint |
| Table | Bronze representation of the endpoint resource |

**One script per endpoint.** Parameter variants are separate resources only when payload schema, grain, auth, or incremental behavior differs.

#### Canonical naming

Script name, dlt resource name, Bronze table name, archive `{endpoint}` segment, and dbt `source()` table name use the **same** resource identifier.

| Resource | Script | Bronze table | Archive segment | Notes |
|---|---|---|---|---|
| `products` | [`products.py`](../branches/dlt_dbt_clickhouse/dlt/route/products.py) | `products` | `products` | **Implemented** (ClickHouse branch) — reference pipeline |
| `categories` | `categories.py` | `categories` | `categories` | Public catalog — must mirror products norms |
| `brands` | `brands.py` | `brands` | `brands` | Public catalog — must mirror products norms |
| `subcategories` | `subcategories.py` | `subcategories` | `subcategories` | Optional catalog follow-on |
| `orders` / cart / wishlist / addresses | TBD | TBD | TBD | JWT — after catalog verified |

Mandatory patterns for every new Route (and other source) endpoint script: [dlt-extraction.md](dlt-extraction.md) **Reference pipeline**.

### Catalog-first sequencing

**First verified dlt slice:** Route `products` → MinIO archive + ClickHouse Bronze + observability lake/OTLP.

**Next catalog endpoints:** `categories`, `brands` — copy `products.py` norms (do not invent a second style).

**Follow-on:** authenticated entities (cart, wishlist, orders, addresses, customer profile) once catalog → Bronze → staging → basic Gold is solid.

Do not block the first green path on JWT signup, demo-user strategy, or payment/checkout flows.

### Multi-source isolation

- Route owns `dlt/route/`, `raw_route_{env}` (ClickHouse) or `nexus_{env}.raw_route` (Iceberg), and `stg_route_*`.
- A later secondary REST source (for example DataForSEO or another ecommerce-adjacent API) gets its own source folder and Bronze/staging databases/schemas.
- Adding a second source **must not** modify Route pipelines or `stg_route_*` models.
- Shared Gold / marts may combine sources. Dims stay entity-grained (`dim_product`), not `route_dim_product`. See [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md).

## 2. Common dlt rules

Route follows the org extraction standard in [dlt-extraction.md](dlt-extraction.md) (including the **Reference pipeline** checklist derived from `products.py`):

- dlt owns REST auth (when needed), pagination, retries, rate limits, incremental state, raw archival, and Bronze loads
- Extract once; dual-write **archive first**, then Bronze; assert `LoadInfo` on each destination
- Shared `run_id` via `--run-id` / `NEXUS_RUN_ID` / mint; stamp audit columns; publish lake on ok and fail
- Archive objects and historical Bronze rows are immutable / append-only

Do not invent a custom watermark system. Do not put business dimensional logic in dlt.

### Pagination and response shape

Route list endpoints return JSON shaped like `{ results, metadata, data: [...] }` with page-number metadata (`numberOfPages`, etc.). `products.py` uses dlt `PageNumberPaginator` + `data_selector="data"`. Confirm live metadata fields when adding `categories` / `brands`.

## 3. Branch destinations

### `dlt_dbt_clickhouse`

| Concern | Contract |
|---|---|
| Code | `branches/dlt_dbt_clickhouse/dlt/route/` |
| Archive bucket | `nexus-dlt-dbt-clickhouse-{env}` |
| Archive prefix | `route/{endpoint}/dt=.../run_id=.../part-*.jsonl.gz` |
| Bronze | `raw_route_{env}.{endpoint}` |
| Staging | `stg_route_{env}.stg_*` under `models/staging/route/` |
| Gold / marts | Shared `gold_{env}`, `marts_{env}` (not source-prefixed DBs) |

### `dlt_dbt_spark_iceberg`

| Concern | Contract |
|---|---|
| Code | `branches/dlt_dbt_spark_iceberg/dlt/route/` (independent copy) |
| Archive | Capability archive bucket; prefix `route/{endpoint}/...` |
| Bronze | `nexus_{env}.raw_route.{endpoint}` |
| Staging | `nexus_{env}.stg_route.stg_*` |
| Gold / marts | Shared schemas `gold`, `marts` in `nexus_{env}` |

Do not start lakehouse Route implementation until ClickHouse Route is verified ([roadmap.md](roadmap.md)).

## 4. Illustrative Gold / marts (not built)

Catalog slice (when modeled):

- `dim_product`, `dim_category`, `dim_brand`
- Optional product-related facts/marts as requirements demand

Later authenticated / transactional modeling examples:

- `dim_customer`, `dim_address`, `dim_date`
- `fact_orders`, `fact_order_items`, `fact_cart`, `fact_wishlist`
- `mart_sales`, `mart_customer_360`, `mart_product_performance`

SCD / soft-delete / hash-key enhancements are **not** part of the current contract. See [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md).

## 5. Orchestration and observability

When implemented:

- Airflow: one DAG per source (e.g. `nexus_route_clickhouse`); tasks per endpoint; dbt selectors; final `observability_publish`
- DAG `run_id` = `NEXUS_RUN_ID` when orchestrated
- Telemetry via `common/observability` → MinIO `nexus-telemetry-{env}` only

## 6. Future secondary sources

GitHub, PokeAPI, and DataForSEO are **not** current primary sources. DataForSEO (digital marketing / SEO) remains a possible future secondary source under the multi-source isolation rules above. Do not reintroduce retired stub folders without a deliberate source contract doc.
