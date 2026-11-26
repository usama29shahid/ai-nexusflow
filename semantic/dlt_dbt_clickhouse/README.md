# Cube Core — warehouse semantic layer

Branch: `dlt_dbt_clickhouse`. Self-hosted Cube Core (`cubejs/cube:v1.8.8`) over ClickHouse `gold_{env}`. Cube reads ClickHouse as `nexus_reader`. It does not use Postgres.

Cubes: `products`, `categories`, `brands`, `subcategories`, `product_images`, `product_subcategories`. Each reads the full SCD2 table. Current measures filter `is_active = 1`. Natural keys are not Cube `primary_key` values, because SCD2 keeps multiple versions per key. Measure names and descriptions match `docker/openmetadata/route_governance.yml`. Dev mode runs that SQL on each playground or API query. Restart Cube only when these model files change (`./scripts/start.sh cube`). There is no refresh DAG.

The Iceberg branch gets its own folder, `semantic/dlt_dbt_spark_iceberg/`, only after that branch has a gold product table.

Dev mode is on. The playground has no app login of its own. It listens on the Compose network at `cube:4000`. The host does not publish that port. `cube.${NEXUS_PUBLIC_HOST}` asks for the same Caddy popup as dbt docs and Elementary (Vault `docs_basic_auth`).

Add `cube` to `COMPOSE_PROFILES` in `.env`, then:

```bash
./scripts/start.sh
```

Or start Cube alone:

```bash
./scripts/start.sh cube
```

Playground: `http://cube.${NEXUS_PUBLIC_HOST:-localhost.com}` after `./scripts/start.sh proxy` (hosts entry from `./scripts/proxy-hosts.sh`). From a laptop, the existing Caddy tunnel (`-L 8080:127.0.0.1:80`) is enough. Drop `-L 4000:127.0.0.1:4000` from the SSH command; that forward no longer reaches Cube.

SQL API (Postgres protocol, not a Postgres database): Compose host `cube`, port `15432`, database `cube`, user `cube`. The password is Vault `secret/nexusflow/{env}/cube_sql`. The host does not publish port 15432.

Measures on cube `products` include `product_count`, `units_sold`, `avg_price`, and `catalog_sales` (current rows). Dimensions: `product_id`, `title`, `brand_name`, `category_name`. The other cubes expose the current, version, and deleted counts for that dim or bridge.
