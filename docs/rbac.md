# Role-based access (RBAC) — held

**Status: held.** Engine RBAC is not implemented and is **not** a Milestone 1 or capstone requirement. Live security is [HashiCorp Vault](vault.md) (secrets). ClickHouse and MinIO stay on the shared bootstrap users.

Related: [vault.md](vault.md), [environments.md](environments.md), [roadmap.md](roadmap.md), [dbt-modeling.md](dbt-modeling.md).

Do **not** add ClickHouse users, GRANT scripts, nested Vault paths, or MinIO IAM policies while this document is held. Do not treat the rest of this page as a cutover runbook.

---

## Current state (what actually runs)

| Surface | Today |
| --- | --- |
| Secrets | Vault KV + Agent, or `.env` when `NEXUS_SECRETS_BACKEND=env` |
| ClickHouse | `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` (typically `default`) |
| MinIO | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` for archive, telemetry, Airflow logs, lakehouse |
| dlt | One process, **two** destinations: ClickHouse **and** MinIO — both of the above env sets |

Vault answers how credentials are stored. It does not grant `SELECT`/`INSERT` or bucket write. Those privileges are whatever the shared users already have.

---

## Secrets vs authorization (intent)

| Layer | Question | Now | If ever cut over |
| --- | --- | --- | --- |
| Secrets | How are passwords injected? | Vault Agent → env | Same; extra **sibling** KV secrets |
| Authorization | What may that identity do? | Shared admin-class users | Engine roles (ClickHouse / MinIO / later Polaris+Trino) |

Snowflake/IAM often blend both. This project splits them on purpose. Portfolio line that matches **today:** secrets in Vault, not in git. Least-privilege **engine** roles are future, not current.

---

## Why this is held

1. **Vault paths** — Live secrets are flat (`secret/nexusflow/{env}/clickhouse`, `…/minio`). Nested paths such as `clickhouse/loader` conflict with that leaf. A later cutover must add **siblings** (`clickhouse_loader`, …) and keep the existing `clickhouse` / `minio` secrets for Compose.
2. **ClickHouse grants** — Staging in this repo is **views** (`+materialized: view` in `branches/dlt_dbt_clickhouse/dbt_project.yml`). Transformer privileges would need `CREATE VIEW` (and likely `ALTER`/`DROP`, `CREATE DATABASE` ownership, `CREATE USER` + `DEFAULT ROLE`). `CREATE TABLE` alone is not enough. Verify against Compose ClickHouse before any SQL.
3. **MinIO** — Root is wired in dlt, `common/observability`, Airflow remote logs, and lakehouse Compose. Splitting access keys is a large change. A thin later slice is ClickHouse roles only; **MinIO stays root**.

---

## Future model (intent only — do not implement now)

Logical roles: `admin` (bootstrap), `loader` (dlt Bronze), `transformer` (dbt), `reader` (Gold/marts). MinIO writers for archive / telemetry / Airflow logs map to those intents; physical names may differ.

If Milestone 1 is verified and you still want a demo:

- ClickHouse loader vs transformer vs reader first.
- dlt still needs **ClickHouse loader + MinIO writer** env vars together (MinIO may remain root).
- Do not start Polaris/Trino RBAC before the lakehouse stack runs.

Out of scope unless a later requirement forces it: SSO, column/row masking, custom auth, using Streamlit/Supabase login as warehouse RBAC.

---

## Implementation status

| Status | Item |
| --- | --- |
| Done | Vault secrets injection |
| Held | This document (intent only) |
| Not started | ClickHouse roles, sibling Vault passwords, MinIO policies, Polaris/Trino |

Read this before adding “security” scaffolding that invents a different role model or changes Vault layout.
