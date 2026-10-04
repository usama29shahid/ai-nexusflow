# Role-based access (RBAC)

**Status: implemented for ClickHouse and MinIO (dev)** — ClickHouse loader / transformer / reader / catalog / admin; MinIO loader / reader / platform_reader / admin.  
Implementation record: [bronze-silver-cutover.md](bronze-silver-cutover.md) (ClickHouse). Bootstrap: `./scripts/clickhouse-rbac-bootstrap.sh` and `./scripts/minio-iam-bootstrap.sh` (pipes credentials; no password tempfile).

Related: [vault.md](vault.md), [environments.md](environments.md), [observability.md](observability.md), [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md).

**Password rotation (VPS):** change KV in Vault UI → reload Agent → `source scripts/load-secrets.sh` → re-run `./scripts/clickhouse-rbac-bootstrap.sh` and, for MinIO IAM, `./scripts/minio-iam-bootstrap.sh`. Then recreate `otel-collector` (and Airflow / lakehouse, if up) so Compose sees the new loader secret. Details: [vault.md](vault.md) (Daily operations).

**MinIO IAM:** implemented — four IAM users + root for bootstrap. Usernames have no `_dev` / `_prd` suffix; `NEXUS_ENV` is on the bucket name. Keys are Vault KV only. **Application code never uses admin or root.** Log expiry is a later MinIO lifecycle rule, not a loader `DeleteObject` grant on append-only buckets.  
**Lakehouse (Polaris/Trino) catalog RBAC:** who may create namespaces — backlog item **6**. MinIO S3 credentials for Polaris/Spark/Trino already use `nexus_loader`.  
**SSO / row-column masking:** out of scope unless a later requirement forces it.

---

## Secrets vs authorization

| Layer | Question | Mechanism |
| --- | --- | --- |
| Secrets | How are passwords injected? | Vault Agent → `.nexusflow/secrets.env` (`NEXUS_SECRETS_BACKEND=vault`; required for MinIO writers) |
| Authorization | What may that identity do? | ClickHouse users + GRANTs; MinIO IAM policies |

dlt and dbt do **not** switch roles at runtime. Each process connects as a **different user**.

---

## Current state

| Surface | Credential |
| --- | --- |
| ClickHouse | `nexus_loader` / `nexus_transformer` / `nexus_reader` / `nexus_catalog` / `nexus_admin` |
| MinIO data plane (all five buckets) | `nexus_loader` (process write) |
| MinIO lake replay | `nexus_reader` (telemetry + index markers) |
| MinIO demo / share (all buckets read-only) | `nexus_platform_reader` |
| MinIO break-glass | `nexus_admin` |
| MinIO server + bucket create | Root (`MINIO_ROOT_*`) only |
| dlt | CH **loader** + MinIO **loader** |
| Polaris / Spark / Trino (S3) | MinIO **loader** |
| dbt | CH **transformer** |
| OpenMetadata catalog ingest | CH **catalog** (`nexus_catalog`) |
| Compose bootstrap | Shared `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` (admin seed only) |

---

## Why these MinIO roles (not per-bucket, not admin-in-code)

Industry practice for this platform: **least-privilege process identities**, **separate secrets per system**, **break-glass offline**, **one shareable read-only identity for demos**.

| Choice | Why |
| --- | --- |
| Same names as ClickHouse (`nexus_loader` / `nexus_reader` / `nexus_admin`) | One mental model; different Vault secrets so a leaked MinIO password does not open ClickHouse |
| One loader spanning all five data buckets | Warehouse + lakehouse + telemetry + Airflow logs are the platform write plane. Per-bucket users stay out until a real isolation requirement appears |
| `nexus_platform_reader` | Safe default to share for “see all buckets, cannot change anything” |
| `nexus_reader` | Process identity for lake-replay scripts (must write index markers) |
| Admin / root in app code | Out — would make IAM policies documentation-only |

### Demo / share

| Goal | Share |
| --- | --- |
| See all buckets, read-only | `nexus_platform_reader` |
| Telemetry / lake-replay style look | `nexus_reader` (narrower; can write index markers) |
| Ops emergency | `nexus_admin` (can write; rotate after) |
| Never share | `nexus_loader`, root |

Durable users are named roles in bootstrap + Vault. Do not create undocumented one-off MinIO users for demos.

---

## ClickHouse users (locked)

| User | Process | Privileges (intent) |
| --- | --- | --- |
| `nexus_loader` | **dlt only** | CREATE/INSERT on `bronze_{env}` (+ dlt metadata as needed); no write to silver/gold |
| `nexus_transformer` | **dbt only** | SELECT `bronze_{env}`; DDL/DML on `silver_{env}`, `elementary_{env}`, and later gold/marts/published/intermediate |
| `nexus_reader` | Consumers (BI/apps) | SELECT on `gold_{env}` / `marts_{env}` / `published_{env}` |
| `nexus_catalog` | **OpenMetadata only** | SELECT/SHOW on `system.*` + `bronze_{env}` / `silver_{env}` / `gold_{env}` / `elementary_{env}` (+ intermediate/marts/published) (no writes) |
| `nexus_admin` | Break-glass / bootstrap | Full CH; create users and GRANTs |

```text
dlt  →  nexus_loader       →  bronze_{env}
dbt  →  nexus_transformer  →  read bronze; write silver / elementary / (later gold+)
BI   →  nexus_reader       →  read gold / marts / published
OM   →  nexus_catalog      →  read system + bronze / silver / gold / elementary (catalog only)
ops  →  nexus_admin        →  break-glass
```

---

## MinIO users (locked)

| User | Process / use | Privileges (intent) |
| --- | --- | --- |
| `nexus_loader` | dlt archive, observability lake writes, OTel `awss3`, Airflow logs, Polaris/Spark/Trino S3 | Put/Get/List/multipart on all five buckets; Delete on Iceberg warehouse only; Deny Delete on warehouse archive, telemetry, Iceberg archive |
| `nexus_reader` | Lake-replay ingest scripts | Get/List telemetry; Put (and OpenObserve Delete) under `indexes/{signoz,openobserve,openmetadata}/` |
| `nexus_platform_reader` | Demo / share | Get/List on all five buckets; no writes |
| `nexus_admin` | Break-glass | Full object access on all five buckets |
| root | Server + `minio-init` + IAM bootstrap | Create buckets and users |

```text
dlt / OTel / Airflow / Polaris / Spark / Trino  →  nexus_loader
lake replay scripts                             →  nexus_reader
demo share (all buckets read-only)              →  nexus_platform_reader
ops break-glass                                 →  nexus_admin
server + bucket create                          →  MINIO_ROOT_*
```

---

## Vault paths (siblings, not nested leaves)

Under `secret/nexusflow/{env}/` add siblings:

| KV path | Env vars |
| --- | --- |
| `clickhouse_loader` | `CLICKHOUSE_LOADER_USER`, `CLICKHOUSE_LOADER_PASSWORD` |
| `clickhouse_transformer` | `CLICKHOUSE_TRANSFORMER_USER`, `CLICKHOUSE_TRANSFORMER_PASSWORD` |
| `clickhouse_reader` | `CLICKHOUSE_READER_USER`, `CLICKHOUSE_READER_PASSWORD` |
| `clickhouse_catalog` | `CLICKHOUSE_CATALOG_USER`, `CLICKHOUSE_CATALOG_PASSWORD` |
| `clickhouse_admin` | `CLICKHOUSE_ADMIN_USER`, `CLICKHOUSE_ADMIN_PASSWORD` |
| `minio_loader` | `MINIO_LOADER_USER`, `MINIO_LOADER_PASSWORD` |
| `minio_reader` | `MINIO_READER_USER`, `MINIO_READER_PASSWORD` |
| `minio_platform_reader` | `MINIO_PLATFORM_READER_USER`, `MINIO_PLATFORM_READER_PASSWORD` |
| `minio_admin` | `MINIO_ADMIN_USER`, `MINIO_ADMIN_PASSWORD` |
| `openmetadata` | `OPENMETADATA_ADMIN_EMAIL`, `OPENMETADATA_ADMIN_PASSWORD` |

Keep existing `clickhouse` and `minio` secrets for Compose/bootstrap as needed.  
**Do not** use nested paths like `clickhouse/loader` (conflicts with the flat `clickhouse` leaf).

---

## Observability alignment

| Surface | Credential |
| --- | --- |
| MinIO archive + telemetry + Airflow logs + Iceberg S3 | `nexus_loader` |
| Lake-replay scripts | `nexus_reader` (telemetry + index markers) |
| Demo share all buckets | `nexus_platform_reader` |
| Elementary models in ClickHouse | `nexus_transformer` (dbt) |
| OTLP / lake JSON events | `common/observability` + Collector — no direct SigNoz/OM API calls |
| SigNoz / OpenObserve / OpenMetadata / Elementary **UI** | Product setup: backlog items **2–3** done / **9** for docs auth; artifact/OTLP producers already live with `products` |

---

## Terraform / GitHub Actions

Compatible: one codebase; `NEXUS_ENV` selects `bronze_{env}` / `silver_{env}`. Terraform and Actions are **additive** — order in [backlog.md](backlog.md); naming rules in [environments.md](environments.md).

- **Airflow** (or a host `./scripts/start.sh` command) runs ingest and transform. The loader process already uses `CLICKHOUSE_LOADER_*`; dbt already uses `CLICKHOUSE_TRANSFORMER_*`.
- **GitHub Actions** (backlog **10**) lints, tests, and deploys the VPS. It does **not** become a second ingest or transform runner. If a workflow injects secrets, it injects those same env vars into `start.sh`.
- **Local Terraform** (backlog **5**) can create the same ClickHouse users/GRANTs and MinIO IAM users/policies and write the existing Vault sibling paths. It does not invent new role names that would force dlt/dbt credential rewrites. Dual ownership with bootstrap scripts is a known issue to resolve when item **5** is implemented — see [backlog.md](backlog.md) item 5.

---

## Implementation status

| Status | Item |
| --- | --- |
| Done (dev) | ClickHouse CREATE USER/GRANT; MinIO IAM (loader / reader / platform_reader / admin); Vault siblings; dlt + lakehouse S3 + OTel + Airflow logs = `nexus_loader`; lake replay = `nexus_reader`; demo share = `nexus_platform_reader` |
| Canonical | This document; ClickHouse record [bronze-silver-cutover.md](bronze-silver-cutover.md) |
| Scheduled | Polaris/Trino **catalog** RBAC — backlog **6**. Log expiry (MinIO ILM) — later |
| Out of scope | SSO/masking; per-bucket user matrix unless required |
