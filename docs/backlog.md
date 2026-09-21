# Local platform backlog

**Status:** documented — execute **one item at a time**.  
**Source of truth for delivery order:** this document. Historical portfolio labels in [roadmap.md](roadmap.md) remain for context; they must **not** block this backlog.

**Git guardrail:** every implementation slice runs on a **feature branch**. Never execute backlog work on `main` until the user explicitly confirms. See [AGENTS.md](../AGENTS.md#git-and-plan-execution-guardrails).

---

## Done

| # | Item |
| --- | --- |
| 0 | Warehouse Route `products` — dlt → MinIO archive + ClickHouse Bronze/silver/Gold + Airflow `route_clickhouse_products` + lake producers |

---

## Ordered backlog

```text
1.  Stack verify — all local Compose services healthy
2.  SigNoz ready — OTLP live dashboards + lake→SigNoz ingest + products run visibility
3.  OpenMetadata ready — catalog warehouse tables from products
4.  MinIO IAM — admin / reader / loader-style (mirror ClickHouse RBAC)
5.  Local Terraform — API-managed resources; HashiCorp Terraform (BSL) only
6.  Iceberg branch parity — products-style path + Airflow + readers + RBAC + TF
7.  Remaining Route REST endpoints — categories, brands, …
8.  Facts, marts, semantic layer — RAG-ready metrics (dbt semantic layer)
9.  Basic auth — Elementary + dlt/dbt docs HTML (Caddy) before public/VPS
10. VPS + GitHub Actions — both branches E2E + service validation
11. Supabase + Streamlit shell — auth/session + portfolio/control UI
12. Later: RAG / multi-agent — consumes semantic layer + docs standards
```

Execute **one number at a time**. Do not start the next item until the current one is verified on its feature branch. Open a PR when asked; **merge to `main` only when the user explicitly confirms**.

---

## Why this order

1. **Readers (2–3) before MinIO IAM / Terraform** — telemetry and warehouse tables already exist from `products`.
2. **MinIO IAM (4) before Terraform (5)** — design roles, prove with scripts, then Terraform owns them (one owner per resource class).
3. **Terraform before Iceberg ELT (6)** — reuse bucket/IAM/env patterns on the lakehouse path.
4. **Endpoints (7) before facts/semantic (8)** — category/brand grains feed dimensional models.
5. **Semantic layer before RAG (12)** — agents ground on declared metrics, not ad-hoc SQL.
6. **Docs basic auth (9) before VPS (10)** — [edge-proxy.md](edge-proxy.md) requires a gate on `docs.` / `elementary.` before public DNS.
7. **VPS + Actions after a fuller local platform** — avoid redeploying while endpoints/facts/auth still churn. Alternate (VPS right after Iceberg) only if Hostinger practice is the immediate goal.
8. **Supabase + Streamlit (11) before RAG** — app auth + UI shell; not a second telemetry store.

---

## Compose vs Terraform

| Layer | Owner |
| --- | --- |
| Run containers (MinIO, ClickHouse, Polaris, SigNoz, OTel, OpenMetadata, Vault, Airflow, …) | **Docker Compose** + `./scripts/start.sh` |
| API-managed resources (buckets, MinIO IAM, ClickHouse DBs/users, optional OM connectors) | **HashiCorp Terraform** (local `environments/dev` first) |
| Pull code, recreate stacks, `uv sync` on VPS | **GitHub Actions** + `start.sh` + host `uv` — **not** Terraform |

**Locks:** HashiCorp Terraform only (BSL 1.1) — free for internal/CI use. **No OpenTofu. No Ansible.**

---

## Work package notes

### 1. Stack verify

Confirm health for profiles in daily use: MinIO + OTel, `clickhouse`, `airflow`, `signoz`, `openmetadata`, optional `vault`, `lakehouse`. Fix or document gaps in [operations.md](operations.md).

### 2. SigNoz ready

Compose profile + live OTLP forward already exist ([docker/signoz/](../docker/signoz/), [docker/otel/collector-config.signoz.yaml](../docker/otel/collector-config.signoz.yaml)). Item **2** finishes the **reader** story for SigNoz. Pipeline code must still not call SigNoz APIs ([observability.md](observability.md)).

**In scope (both paths + product polish):**

| # | Deliverable |
| --- | --- |
| 2a | **Live OTLP:** SigNoz up → collector forwards → run `route_clickhouse_products` (or host dlt) → traces/metrics visible in SigNoz UI |
| 2b | **Dashboards / saved views** for the products pipeline run (enough to demo ops visibility; document how to open them) |
| 2c | **Lake → SigNoz ingest:** implement `./scripts/observability-ingest.sh signoz` — replay/project lake OTLP (and related) objects from `nexus-telemetry-{env}` into SigNoz’s native store so runs that happened while SigNoz was down (or after a SigNoz wipe) can be indexed |
| 2d | Smoke/docs: how to start SigNoz, verify live path, run lake ingest, confirm UI; update [docker/signoz/README.md](../docker/signoz/README.md) / [observability.md](observability.md) |
| 2e | Keep lake writes required on every run whether or not SigNoz is up |

**Done when:** live OTLP path verified on a products run **and** `observability-ingest.sh signoz` successfully indexes lake data into SigNoz (documented + repeatable).

**Out of scope for item 2:** OpenMetadata (item **3**); Elementary HTML auth (item **9**); changing dlt/dbt emit code to call SigNoz directly.

### 3. OpenMetadata ready

Connect ClickHouse (later Iceberg/Trino); show warehouse models from the products run. Reader-only.

### 4. MinIO IAM

Lift deferral in [rbac.md](rbac.md). Parallel ClickHouse intent: loader write, reader read, admin break-glass. Vault sibling paths when `NEXUS_SECRETS_BACKEND=vault`.

### 5. Local Terraform

Modules under `infrastructure/terraform/` against local endpoints. Hostinger DNS/edge and Actions stay in item **10**. HashiCorp Terraform only (BSL); no OpenTofu/Ansible.

**Known issue — dual ownership (resolve when implementing item 5):**

Today two paths create the same resource classes:

| Resource | Current owner |
| --- | --- |
| MinIO buckets | Compose `minio-init` → `docker/minio/init/create-buckets.sh` |
| ClickHouse DBs + users/GRANTs | `./scripts/clickhouse-rbac-bootstrap.sh` |

Terraform will also manage buckets, MinIO IAM, and ClickHouse DBs/users. **Do not decide the cutover in advance of implementation** — when item **5** starts, plan explicitly so only **one** owner Creates each resource class. Likely options to evaluate then:

1. `terraform import` existing resources, then disable/no-op init + RBAC bootstrap for TF-managed objects  
2. Narrow scripts to “ensure TF applied” / drift check only  
3. Avoid dual Create (TF apply fighting Compose init on every restart)

Document the chosen approach in `infrastructure/terraform/README.md` when item **5** lands. Until then, keep current scripts as the live path.

### 6. Iceberg branch parity

Enable `dlt_dbt_spark_iceberg`; products-style dlt → Iceberg → dbt-spark → Trino; Airflow; lake; readers; Polaris/MinIO RBAC; extend Terraform ([dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md)).

### 7. Remaining Route endpoints

Copy warehouse `products` norms ([dlt-extraction.md](dlt-extraction.md)); one DAG per endpoint; mirror on Iceberg when warehouse path is proven.

### 8. Facts, marts, semantic layer

Add `fct_*` / marts per [dbt-modeling.md](dbt-modeling.md); dbt semantic models + metrics for RAG. Warehouse first.

### 9. Basic auth for docs

Caddy gate for Elementary HTML, dbt docs, dlt docs. Local `proxy` first; required before VPS public hostnames ([edge-proxy.md](edge-proxy.md)).

### 10. VPS + GitHub Actions

Edge/env Terraform for VPS + Actions lint/test/build/apply/deploy. Validate both branches’ first Airflow jobs and all services.

### 11. Supabase + Streamlit

Supabase auth/session; Streamlit portfolio/control UI. Not pipeline telemetry storage.

### 12. RAG (later)

Multi-agent + RAG over `docs/` + semantic layer. Do not start before items 8 and 11 are in place.

---

## Explicit non-goals (until listed above)

- OpenTofu or Ansible
- Terraform as app deploy / Compose / `uv` updater
- Pipeline code calling SigNoz or OpenMetadata APIs
- LLM/RAG before semantic layer + Streamlit shell
- Speculative stubs that skip verification of the current backlog item
