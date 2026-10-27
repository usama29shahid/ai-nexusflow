# Cube Core — warehouse semantic layer

Branch: `dlt_dbt_clickhouse`. Self-hosted Cube Core (`cubejs/cube:v1.8.8`) over ClickHouse `gold_{env}`. Cube reads ClickHouse as `nexus_reader`. It does not use Postgres.

Cubes: `products`, `categories`, `brands`, `subcategories`, `product_images`, `product_subcategories`. Each reads the full SCD2 table. Current measures filter `is_active = 1`. Natural keys are not Cube `primary_key` values, because SCD2 keeps multiple versions per key. Measure names and descriptions match `docker/openmetadata/route_governance.yml`. Dev mode runs that SQL on each playground or API query. Restart Cube only when these model files change (`./scripts/start.sh cube`). There is no refresh DAG.

The Iceberg branch gets its own folder, `semantic/dlt_dbt_spark_iceberg/`, only after that branch has a gold product table.

Dev mode is on. The playground has no app login. Publish it on `127.0.0.1` only. Public access uses the same Caddy basic auth as Elementary, dbt docs, and dlt docs (backlog item **9**). Do not put port 4000 on a public address before that gate exists.

Add `cube` to `COMPOSE_PROFILES` in `.env`, then:

```bash
./scripts/start.sh
```

Or start Cube alone:

```bash
./scripts/start.sh cube
```

Playground on the instance: `http://127.0.0.1:4000`. With the `proxy` profile, the same UI is `http://cube.${NEXUS_PUBLIC_HOST:-localhost.com}` (hosts entry from `./scripts/proxy-hosts.sh`).

From a laptop, forward that port with the other UIs (`docs/operations.md`):

```bash
ssh -L 4000:127.0.0.1:4000 nexus-ec2
```

Then open `http://127.0.0.1:4000` in the laptop browser.

SQL API (Postgres protocol, not a Postgres database): host `127.0.0.1`, port `15432`, user `cube`, password `cube`, database `cube`.

Measures on cube `products` include `product_count`, `units_sold`, `avg_price`, and `catalog_sales` (current rows). Dimensions: `product_id`, `title`, `brand_name`, `category_name`. The other cubes expose the current, version, and deleted counts for that dim or bridge.
