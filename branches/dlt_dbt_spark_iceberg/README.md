# dlt_dbt_spark_iceberg — open lakehouse ELT

```text
Source → DLT → MinIO archive + Iceberg Bronze (Polaris nexus_dev.raw_{source})
      → dbt-spark → Iceberg gold / marts → Trino
```

Standards: [docs/dlt-dbt-spark-iceberg.md](../../docs/dlt-dbt-spark-iceberg.md) (includes GitHub `pipe_one` example), [docs/environments.md](../../docs/environments.md). Env: `NEXUS_ENV` (default `dev`). Catalog is `nexus_{env}`; do not suffix Iceberg schemas with `_dev`.

- `dlt/{source}/` — extract pipelines (archive + Iceberg Bronze). Independent of `dlt_dbt_clickhouse`.
- `models/` — dbt (`nexus_lakehouse`, adapter `dbt-spark`)

Spark, Polaris, and Trino Compose services land in Phase 1 Milestone 2. Not implemented yet.

From the repo root (after Spark Thrift exists):

```bash
uv run dbt debug --project-dir branches/dlt_dbt_spark_iceberg
```
