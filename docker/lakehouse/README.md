# lakehouse

Docker config for profile `lakehouse` (`dlt_dbt_spark_iceberg`):

| Path | Role |
| --- | --- |
| `polaris/` | Bootstrap scripts — creates Polaris catalog `nexus_{NEXUS_ENV}` |
| `spark/spark-defaults.conf` | Spark Thrift + Iceberg REST → Polaris |
| `spark/minio-localhost-proxy.py` | Forwards Polarish-vended `localhost:9002` to Compose `minio:9000` |
| `trino/catalog/nexus_dev.properties` | Trino Iceberg connector → Polaris |

Compose services: `polaris`, `polaris-setup`, `spark-thrift`, `trino`.

Polaris OAuth defaults: `root` / `s3cr3t` (must match `POLARIS_CLIENT_SECRET` in `.env` and `spark-defaults.conf` credential line).
