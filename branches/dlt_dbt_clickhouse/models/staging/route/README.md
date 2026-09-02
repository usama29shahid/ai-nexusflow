# staging/route → stg_route_{env}

dbt staging for the Route API source. Models `stg_*` over Bronze `raw_route_{env}` via `source()`.

**Not implemented yet.** Catalog-first when built (`products`, `categories`, `brands`).

Conformed Gold lives in shared `gold_{env}` / `marts_{env}`, not under this folder. Other REST sources keep separate `staging/{source}/` trees and must not change Route staging. See [docs/route-ingestion.md](../../../../docs/route-ingestion.md) and [docs/enhanced-modeling-strategy.md](../../../../docs/enhanced-modeling-strategy.md).
