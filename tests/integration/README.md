# tests/integration

Service-level tests against Compose. Python/dlt/dbt stay on the **host**.

## dlt ClickHouse smoke (no REST)

Requires profile `clickhouse` (MinIO always on):

```bash
set -a && source .env && set +a
export NEXUS_ENV="${NEXUS_ENV:-dev}"
export NEXUS_RUN_ID="${NEXUS_RUN_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
uv run python tests/integration/dlt_clickhouse_smoke.py
```

Writes in-memory rows to ClickHouse (`{CLICKHOUSE_DB}.raw_dlt_smoke_{env}___smoke`) and JSONL in `s3://nexus-dlt-dbt-clickhouse-{env}`.

dbt staging (one model on that Bronze table):

```bash
uv run dbt run --project-dir branches/dlt_dbt_clickhouse \
  --profiles-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
  --select stg_dlt_smoke_smoke --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
uv run dbt test --project-dir branches/dlt_dbt_clickhouse \
  --profiles-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
  --select stg_dlt_smoke_smoke source:dlt_smoke_raw
```

## dlt lakehouse smoke (no REST)

Requires profile `lakehouse` (Polaris, Spark Thrift, Trino; MinIO always on):

```bash
set -a && source .env && set +a
export NEXUS_ENV="${NEXUS_ENV:-dev}"
export NEXUS_RUN_ID="${NEXUS_RUN_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
uv run python tests/integration/dlt_lakehouse_smoke.py
```

Writes JSONL to `s3://nexus-dlt-dbt-spark-iceberg-archive-{env}` and Iceberg `nexus_{env}.raw_dlt_smoke.smoke` via Polaris.

Check in Trino (after the lakehouse profile is up):

```bash
docker exec trino trino --catalog nexus_dev --execute \
  "SELECT id, name, run_id FROM raw_dlt_smoke.smoke ORDER BY id"
```

**After `docker compose down` + `up`:** Polaris loses in-memory catalog metadata (MinIO files remain). Re-register the smoke table, then wait for Trino (it can take ~60s after `up`):

```bash
./scripts/lakehouse-restore.sh
```

The restore script waits until Trino accepts queries and then runs the SELECT. If you query immediately after `compose up` you may see `Trino server is still initializing` — that is not data loss.

If MinIO has no smoke metadata yet, run `dlt_lakehouse_smoke.py` first.

dbt staging (Spark Thrift → Iceberg `stg_dlt_smoke.stg_dlt_smoke_smoke`):

```bash
uv run dbt run --project-dir branches/dlt_dbt_spark_iceberg \
  --profiles-dir branches/dlt_dbt_spark_iceberg --target "$NEXUS_ENV" \
  --select stg_dlt_smoke_smoke --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
uv run dbt test --project-dir branches/dlt_dbt_spark_iceberg \
  --profiles-dir branches/dlt_dbt_spark_iceberg --target "$NEXUS_ENV" \
  --select stg_dlt_smoke_smoke source:dlt_smoke_raw
```
