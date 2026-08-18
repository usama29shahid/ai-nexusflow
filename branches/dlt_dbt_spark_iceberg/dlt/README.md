# dlt pipelines (this capability)

One folder per REST **source**. One script (or resource) per **endpoint**. Writes MinIO JSONL archive + Iceberg Bronze via Apache Polaris (`nexus_{env}.raw_{source}`).

Do not import pipelines from `branches/dlt_dbt_clickhouse`.
