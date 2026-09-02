# Route — dlt endpoint pipelines → raw_route_{env}

Primary REST source: [Route API](https://ecommerce.routemisr.com/) (synthetic ecommerce demo data). Shared source contract: [docs/route-ingestion.md](../../../../docs/route-ingestion.md).

This folder belongs to `dlt_dbt_clickhouse`. Endpoint pipelines write ClickHouse Bronze `raw_route_{env}` and MinIO archive `nexus-dlt-dbt-clickhouse-{env}`.

**Not implemented yet.** First slice when built: public catalog endpoints (`products`, `categories`, `brands`). Authenticated cart / wishlist / orders / addresses come later.

Secondary REST sources (for example DataForSEO) get their own `dlt/{source}/` folders. They must not modify pipelines here. Shared Gold may combine sources; see [docs/enhanced-modeling-strategy.md](../../../../docs/enhanced-modeling-strategy.md).
