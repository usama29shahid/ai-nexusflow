# dlt_dbt_spark_iceberg — open lakehouse ELT

```text
Source → DLT → MinIO archive + Iceberg Bronze (Polaris nexus_dev.raw_{source})
      → dbt-spark → Iceberg gold / marts → Trino
```

Standards: [docs/dlt-dbt-spark-iceberg.md](../../docs/dlt-dbt-spark-iceberg.md) (includes GitHub `pull_requests` example), [docs/github-ingestion.md](../../docs/github-ingestion.md), [docs/environments.md](../../docs/environments.md). Env: `NEXUS_ENV` (default `dev`). Catalog is `nexus_{env}`; do not suffix Iceberg schemas with `_dev`.

- `dlt/{source}/` — extract pipelines (archive + Iceberg Bronze). Independent of `dlt_dbt_clickhouse`.
- `models/` — dbt (`nexus_lakehouse`, adapter `dbt-spark`). SQL via Spark Thrift by default; PySpark only for complex `.py` models.

Spark Thrift / Polaris / Trino: Docker profile `lakehouse` (see [docs/setup.md](../../docs/setup.md)).

dbt needs profile `nexus_lakehouse` in `~/.dbt/profiles.yml`, or a local copy. Source `.env` first (dbt does not load it):

```bash
cd ~/projects/ai-nexusflow
set -a && source .env && set +a
cp branches/dlt_dbt_spark_iceberg/profiles.example.yml branches/dlt_dbt_spark_iceberg/profiles.yml   # once; gitignored
uv run dbt debug --project-dir branches/dlt_dbt_spark_iceberg
# or: --profiles-dir branches/dlt_dbt_spark_iceberg
```

Smoke staging (after lakehouse DLT smoke + `./scripts/lakehouse-restore.sh` if you restarted Compose):

```bash
export NEXUS_ENV="${NEXUS_ENV:-dev}"
export NEXUS_RUN_ID="${NEXUS_RUN_ID:-local}"
uv run dbt run --project-dir branches/dlt_dbt_spark_iceberg \
  --profiles-dir branches/dlt_dbt_spark_iceberg --target "$NEXUS_ENV" \
  --select stg_dlt_smoke_smoke --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
uv run dbt test --project-dir branches/dlt_dbt_spark_iceberg \
  --profiles-dir branches/dlt_dbt_spark_iceberg --target "$NEXUS_ENV" \
  --select stg_dlt_smoke_smoke source:dlt_smoke_raw
```
