# Role-based access (RBAC)

**Status: implemented for ClickHouse (dev)** — loader / transformer / reader / admin.  
Implementation record: [bronze-silver-cutover.md](bronze-silver-cutover.md). Bootstrap: `./scripts/clickhouse-rbac-bootstrap.sh` (pipes SQL into `clickhouse-client`; no password tempfile).

Related: [vault.md](vault.md), [environments.md](environments.md), [observability.md](observability.md), [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md).

**Password rotation (VPS):** change KV in Vault UI → reload Agent → `source scripts/load-secrets.sh` → re-run `./scripts/clickhouse-rbac-bootstrap.sh`. Details: [vault.md](vault.md) (Daily operations).

**MinIO IAM:** out of scope — keep shared root.  
**Lakehouse (Polaris/Trino) RBAC:** not started.  
**SSO / row-column masking:** out of scope unless a later requirement forces it.

---

## Secrets vs authorization

| Layer | Question | Mechanism |
| --- | --- | --- |
| Secrets | How are passwords injected? | Vault Agent → env (or `.env` when `NEXUS_SECRETS_BACKEND=env`) |
| Authorization | What may that identity do? | ClickHouse users + GRANTs |

dlt and dbt do **not** switch roles at runtime. Each process connects as a **different user**.

---

## Current state

| Surface | Credential |
| --- | --- |
| ClickHouse | `nexus_loader` / `nexus_transformer` / `nexus_reader` / `nexus_admin` |
| MinIO | Root for archive, telemetry, Airflow logs (unchanged) |
| dlt | CH **loader** + MinIO root |
| dbt | CH **transformer** |
| Compose bootstrap | Shared `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` (admin seed only) |

---

## ClickHouse users (locked)

| User | Process | Privileges (intent) |
| --- | --- | --- |
| `nexus_loader` | **dlt only** | CREATE/INSERT on `bronze_{env}` (+ dlt metadata as needed); no write to silver/gold |
| `nexus_transformer` | **dbt only** | SELECT `bronze_{env}`; DDL/DML on `silver_{env}`, `elementary_{env}`, and later gold/marts/published/intermediate |
| `nexus_reader` | Consumers (BI/apps) | SELECT on `gold_{env}` / `marts_{env}` / `published_{env}` |
| `nexus_admin` | Break-glass / bootstrap | Full CH; create users and GRANTs |

Complexity of this slice: **MEDIUM** (CH only). Full CH + MinIO IAM + lakehouse: **COMPLEX** — deferred.

```text
dlt  →  nexus_loader       →  bronze_{env}
dbt  →  nexus_transformer  →  read bronze; write silver / elementary / (later gold+)
BI   →  nexus_reader       →  read gold / marts / published
ops  →  nexus_admin        →  break-glass
```

---

## Vault paths (siblings, not nested leaves)

Under `secret/nexusflow/{env}/` add siblings:

| KV path | Env vars |
| --- | --- |
| `clickhouse_loader` | `CLICKHOUSE_LOADER_USER`, `CLICKHOUSE_LOADER_PASSWORD` |
| `clickhouse_transformer` | `CLICKHOUSE_TRANSFORMER_USER`, `CLICKHOUSE_TRANSFORMER_PASSWORD` |
| `clickhouse_reader` | `CLICKHOUSE_READER_USER`, `CLICKHOUSE_READER_PASSWORD` |
| `clickhouse_admin` | `CLICKHOUSE_ADMIN_USER`, `CLICKHOUSE_ADMIN_PASSWORD` |

Keep existing `clickhouse` and `minio` secrets for Compose/bootstrap as needed.  
**Do not** use nested paths like `clickhouse/loader` (conflicts with the flat `clickhouse` leaf).

---

## Observability alignment

| Surface | Credential |
| --- | --- |
| MinIO archive + `nexus-telemetry-{env}` | MinIO root (unchanged) |
| Elementary models in ClickHouse | `nexus_transformer` (dbt) |
| OTLP / lake JSON events | `common/observability` + Collector — no direct SigNoz/OM API calls |
| SigNoz / OpenMetadata / Elementary **UI** | After gold for the products pipeline; artifact/OTLP producers from day one |

---

## Terraform / GitHub Actions

Compatible: one codebase; `NEXUS_ENV` selects `bronze_{env}` / `silver_{env}`. Phase 2 is **additive** — see [environments.md](environments.md) (Phase 2 is additive).

- **Airflow** (or a host `./scripts/start.sh` command) runs ingest and transform. The loader process already uses `CLICKHOUSE_LOADER_*`; dbt already uses `CLICKHOUSE_TRANSFORMER_*`.
- **GitHub Actions** lints, tests, and optionally deploys the VPS. It does **not** become a second ingest or transform runner. If a workflow injects secrets, it injects those same env vars into `start.sh`.
- **Terraform** (later) can create the same ClickHouse users/GRANTs and write the existing Vault sibling paths. It does not invent new role names that would force dlt/dbt credential rewrites.

---

## Implementation status

| Status | Item |
| --- | --- |
| Done (dev) | CREATE USER/GRANT, Vault siblings, dlt=`nexus_loader`, dbt=`nexus_transformer` |
| Canonical | This document; record [bronze-silver-cutover.md](bronze-silver-cutover.md) |
| Deferred | MinIO IAM, Polaris/Trino RBAC, SSO/masking |
