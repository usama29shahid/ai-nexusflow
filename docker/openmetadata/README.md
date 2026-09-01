# OpenMetadata (profile: openmetadata)

Data catalog reader. **Reader only** — pipeline code writes to the observability lake; configure warehouse/dbt connectors later.

| | |
| --- | --- |
| UI | http://127.0.0.1:8585 |
| Login | `admin@open-metadata.org` / `admin` |
| Postgres (host) | `127.0.0.1:5433` |
| Elasticsearch (host) | `127.0.0.1:9200` |

Default stack is the catalog UI only (Postgres + small Elasticsearch + server). Typical local RAM is about **1.5–2 GB**, not the official 6 GB quickstart.

Start:

```bash
./scripts/start.sh openmetadata
```

OpenMetadata’s **internal** Airflow (connector jobs) is a separate, optional profile. Do not confuse it with Nexus Airflow on `:8081`:

```bash
docker compose --profile openmetadata-ingestion up -d
# UI: http://127.0.0.1:8089
```

Elasticsearch heap defaults to 256 MB (`OPENMETADATA_ES_JAVA_OPTS`). Raise it only if catalog search is slow.

See [docs/observability.md](../../docs/observability.md).
