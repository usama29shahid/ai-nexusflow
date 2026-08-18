# dbt models (`nexus_lakehouse`)

Folders map to Iceberg schemas (Polaris namespaces), not ClickHouse databases. See [docs/dlt-dbt-spark-iceberg.md](../../../docs/dlt-dbt-spark-iceberg.md) and [docs/dbt-modeling.md](../../../docs/dbt-modeling.md).

```text
staging/{source}/     nexus_{env}.stg_{source}
intermediate/         nexus_{env}.int
gold/                 nexus_{env}.gold
marts/                nexus_{env}.marts
published/            nexus_{env}.pub
```
