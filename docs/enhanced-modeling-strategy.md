# Enhanced modeling strategy (proposal)

**Status: backlog / proposal — not an active implementation contract.**

Do **not** change the current dlt or dbt process until this strategy is reviewed and accepted. Today’s rules remain those in [dlt-extraction.md](dlt-extraction.md), [dbt-modeling.md](dbt-modeling.md), [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), and [AGENTS.md](../AGENTS.md).

This document captures enhancements discussed for enterprise-style dimensional modeling metadata: keys, hashing, SCD variants, soft deletes, audit columns, pipeline-level materialization, and multi-source Gold.

## Why this exists

Phase 1 focuses on a runnable vertical slice: REST → dlt → archive + Bronze → dbt staging / Gold + tests + observability. Optional SCD2 and natural/hashed keys are already allowed by [dbt-modeling.md](dbt-modeling.md) when a requirement needs them.

The YAML-style patterns below are a **future metadata contract** for consistent modeling (and later Phase 2 ELT generation). They are not required for the first Route catalog slice.

## Keys, hashing, and audit (proposal)

```yaml
# PROPOSAL — not implemented. Example only.
business_key:
  - product_id

surrogate_key:
  enabled: true

hashing:
  pk_hash: true
  row_hash: true

scd:
  type: 2   # or 1, 3, 6, … — chosen per model

soft_delete:
  enabled: true
  strategy: source_reconciliation

audit:
  source_system: true
  inserted_on: true
  updated_on: true
  deleted_on: true
  etl_batch_id: true
```

### Concepts

| Concept | Intent |
|---|---|
| Business key | Natural identity from the source (`product_id`, etc.) |
| Surrogate key | Optional warehouse key when natural keys are insufficient or multi-source |
| `pk_hash` | Stable hash of business key(s) for joins / identity |
| `row_hash` | Change detection across tracked attributes |
| Soft delete | Mark absence via reconciliation rather than hard-deleting history |
| Audit | Source system, inserted/updated/deleted timestamps, ETL batch / run id |

**Overlap with today’s contract:** Bronze already stamps `run_id` / `NEXUS_RUN_ID` and dlt load metadata (`_extracted_at`, `_dlt_*`). Enhanced audit columns should extend or alias that story — not invent a parallel batch system without review.

Current policy already prefers **natural or hashed keys over serial surrogates**. This proposal formalizes optional columns and metadata; it does not mandate surrogates on every dim.

## Materialization decided per pipeline / model

Materialization is **not** a global warehouse default. During development, choose per model or pipeline what the requirement needs:

- Incremental strategies (append / merge patterns as the adapter allows — ClickHouse and Spark differ)
- SCD1 (overwrite / current-only)
- SCD2 (history with `valid_from` / `valid_to` / `is_current` — insert-only patterns preferred on ClickHouse)
- SCD3, SCD6, or other SCD variants when a requirement explicitly needs them

Metadata may declare the intended SCD / materialization type. Implementation stays **requirement-driven**: do not scaffold every SCD type for every entity.

Bronze remains append-only history of loads. “Current” and as-of logic stay in dbt downstream (unchanged from today’s modeling doc).

## Soft delete and source reconciliation

When enabled by requirement:

- Prefer soft-delete flags / `deleted_on` over destructive deletes of warehouse history
- `source_reconciliation` means comparing the latest extracted set to prior current rows and marking missing keys deleted — details TBD when this strategy is accepted
- Soft delete does **not** change dlt’s append-only Bronze rule

## Multi-source isolation and shared Gold

Primary source today: **Route** (`route`). Future secondary sources (for example DataForSEO or another ecommerce-adjacent REST API) must compose cleanly.

```text
dlt/route/     → raw_route_{env}     → stg_route_{env}     ──┐
dlt/{other}/   → raw_{other}_{env}   → stg_{other}_{env}   ──┼──► gold_{env} / marts_{env}
                                                              │
                                              optional int_{env} ┘
```

### Isolation boundary (must not break)

| Layer | Ownership |
|---|---|
| `branches/.../dlt/{source}/` | That source only |
| `raw_{source}_{env}` / Iceberg `raw_{source}` | That source only |
| `models/staging/{source}/` → `stg_{source}_*` | That source only |
| Airflow DAG | One DAG per source |

Adding `dataforseo` (or any other REST source) **must not** modify Route ingestion scripts or `stg_route_*` models.

### Shared Gold / marts

- Conformed dims/facts/events live in shared databases/schemas (`gold_{env}`, `marts_{env}`, optional `int_{env}` / `pub_{env}`)
- Models may `ref()` / `source()` from **multiple** stagings
- Dim names stay entity-grained: `dim_product`, not `route_dim_product`
- Use `source_system` (or equivalent) when lineage across APIs matters
- Example: Route feeds transactional ecommerce dims/facts; a later SEO/marketing source can enrich the same marts without rewriting Route Bronze/staging

This restates existing AGENTS / dbt-modeling guidance: Gold is shared by default; do not fork dims per endpoint or per source unless the requirement names a separate dimension.

## Process gate

1. Keep implementing Phase 1 with **current** dlt/dbt contracts (Route catalog-first when coding starts).
2. Review and accept this enhanced strategy (or a revised version).
3. Only then update modeling docs, macros, and generators to treat the YAML patterns as active standards.

## Related

- [dbt modeling](dbt-modeling.md) — current contract
- [route-ingestion.md](route-ingestion.md) — primary source
- [architecture.md](architecture.md) — Phase 2 LLM/RAG consumes accepted standards
- [roadmap.md](roadmap.md)
