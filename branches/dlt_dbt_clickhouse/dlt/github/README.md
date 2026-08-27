# GitHub — dlt endpoint pipelines → raw_github_{env}

The shared GitHub source contract and branch-specific ingestion standards are documented in [docs/github-ingestion.md](../../../../docs/github-ingestion.md).

This folder belongs to the `dlt_dbt_clickhouse` capability. Its endpoint pipelines write the ClickHouse Bronze database `raw_github_{env}` and the MinIO archive `nexus-dlt-dbt-clickhouse-{env}`. GitHub ingestion is not implemented in this folder yet.
