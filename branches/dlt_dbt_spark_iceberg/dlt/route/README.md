# Route (dlt)

Primary REST source: [Route API](https://ecommerce.routemisr.com/). Shared contract: [docs/route-ingestion.md](../../../../docs/route-ingestion.md).

This folder belongs to `dlt_dbt_spark_iceberg`. Planned Bronze: `nexus_{env}.raw_route`, archive under this capability’s archive bucket.

**Not implemented yet.** Catalog-first (`products`, `categories`, `brands`); JWT entities later. Independent of the ClickHouse Route pipelines — same API, separate code.

Secondary sources use their own `dlt/{source}/` folders and must not modify Route here. Shared Gold may combine sources; see [docs/enhanced-modeling-strategy.md](../../../../docs/enhanced-modeling-strategy.md).
