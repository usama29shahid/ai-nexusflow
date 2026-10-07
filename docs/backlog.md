# Local platform backlog

**Status:** documented — execute **one item at a time**.  
**Source of truth for delivery order:** this document. Historical portfolio labels in [roadmap.md](roadmap.md) remain for context; they must **not** block this backlog.

**Git guardrail:** every implementation slice runs on a **feature branch**. Never execute backlog work on `main` until the user explicitly confirms. See [AGENTS.md](../AGENTS.md#git-and-plan-execution-guardrails).

---

## Done

| # | Item |
| --- | --- |
| 0 | Warehouse Route `products` — dlt → MinIO archive + ClickHouse Bronze/silver/Gold + Airflow `route_clickhouse_products` + lake producers |
| 1 | Stack verify — `./scripts/start.sh verify` (MinIO + OTel, ClickHouse, Airflow, SigNoz, OpenMetadata, Vault, lakehouse). `openmetadata-ingestion` stays optional |
| 2 | SigNoz ready — OTLP live + products dashboard + lake→SigNoz ingest (`observability-ingest.sh signoz`) |
| 2.1 | OpenObserve ready — primary observer under test (SigNoz retained); OTLP + dashboards + lake replay |
| 3 | OpenMetadata ready — catalog warehouse tables from products (`observability-ingest.sh openmetadata`) |
| 3.1 | OpenMetadata ELT projection — dbt lineage/DQ results, Airflow (dlt) pipelines, elementary schema + deep-dive links |
| 4 | MinIO IAM — `nexus_loader` / `nexus_reader` / `nexus_platform_reader` / `nexus_admin` (Vault KV only; `./scripts/minio-iam-bootstrap.sh`). Root for bucket create only; Polaris/Spark/Trino S3 use loader |

---

## Ordered backlog

```text
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

1. **Readers (2 → 2.1 → 3) before MinIO IAM / Terraform** — telemetry and warehouse tables already exist from `products`. Items **2–3** are done (SigNoz, OpenObserve primary under test, OpenMetadata catalog). Grafana is deferred until both branches and LLM are running.
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
| Run containers (MinIO, ClickHouse, Polaris, SigNoz, OpenObserve, OTel, OpenMetadata, Vault, Airflow, …) | **Docker Compose** + `./scripts/start.sh` |
| API-managed resources (buckets, MinIO IAM, ClickHouse DBs/users, optional OM connectors) | **HashiCorp Terraform** (local `environments/dev` first) |
| Pull code, recreate stacks, `uv sync` on VPS | **GitHub Actions** + `start.sh` + host `uv` — **not** Terraform |

**Locks:** HashiCorp Terraform only (BSL 1.1) — free for internal/CI use. **No OpenTofu. No Ansible.**

---

## Work package notes

### 1. Stack verify — done

`./scripts/start.sh verify` checks MinIO + OTel, `clickhouse`, `airflow`, `signoz`, `openmetadata`, Vault when `NEXUS_SECRETS_BACKEND=vault`, and `lakehouse`. It does not start or repair services. `openmetadata-ingestion` is skipped (optional heavy OM Airflow; catalog ingest uses a one-shot image — item 3). Runbook: [operations.md](operations.md). SigNoz Compose health uses `curl` because the standalone image has no `wget`.

### 2. SigNoz ready — done

Compose profile + live OTLP forward already existed. Item **2** finished the **reader** story: ensure OTLP ingester, products dashboard, and lake→SigNoz replay. Pipeline code must still not call SigNoz APIs ([observability.md](observability.md)).

**Delivered:**

| # | Deliverable |
| --- | --- |
| 2a | **Live OTLP:** `./scripts/start.sh signoz` → `signoz-ensure` → collector forwards → products run → traces in SigNoz UI (`nexusflow.dlt`) |
| 2b | **Dashboard:** `docker/signoz/dashboards/route-products.json` + `signoz-bootstrap.sh` |
| 2c | **Lake → SigNoz:** `./scripts/observability-ingest.sh signoz` (`scripts/signoz_lake_ingest.py`) |
| 2d | Smoke/docs: [docker/signoz/README.md](../docker/signoz/README.md), [observability.md](observability.md), this backlog note |
| 2e | Lake writes remain required whether or not SigNoz is up |
| 2f | **Ops dashboards (follow-on):** collector self-metrics + httpcheck uptime + Ingestion JSON; bootstrap upserts all `dashboards/*.json`. Deferred (situation-triggered): ClickHouse Prometheus, Docker `docker_stats`, Cursor IDE, CI/CD — see [docker/signoz/README.md](../docker/signoz/README.md#future-dashboards-add-when-the-situation-matches) |

**Done when:** live OTLP path verified on a products run **and** `observability-ingest.sh signoz` successfully indexes lake data into SigNoz (documented + repeatable).

### 2.1 OpenObserve ready — done

Compose profile + live OTLP forward + dashboards + lake replay. **Primary observer under test**; SigNoz (item 2) stays. Pipeline code must still not call OpenObserve APIs ([observability.md](observability.md)). Grafana deferred until both branches + LLM are running.

**Delivered:**

| # | Deliverable |
| --- | --- |
| 2.1a | **Image:** `openobserve/openobserve:v1.0.4` single-binary (not SigNoz-style standalone) |
| 2.1b | **Live OTLP:** `./scripts/start.sh openobserve` → collector forwards → products traces in UI |
| 2.1c | **Dashboards:** products, collector, uptime, ingestion, Docker, Airflow, ClickHouse + `openobserve-bootstrap.sh` |
| 2.1d | **Lake → OpenObserve:** `./scripts/observability-ingest.sh openobserve` |
| 2.1e | **Vault:** KV `secret/nexusflow/{env}/openobserve` → `ZO_ROOT_USER_*` via Agent |
| 2.1f | **Caddy:** `openobserve.${NEXUS_PUBLIC_HOST}` + `proxy-hosts.sh` |
| 2.1g | Smoke/docs: [docker/openobserve/README.md](../docker/openobserve/README.md), observability/ops/vault/edge |

**Done when:** live OTLP verified on a products run **and** lake replay indexes into OpenObserve; SigNoz still works when both profiles are up.

### 3. OpenMetadata ready — done

Compose profile on **2.0.3** + Elasticsearch **9.3.0**. Catalogs warehouse products tables (ClickHouse + lake dbt artifacts). Reader-only. Pipeline code must still not call OpenMetadata APIs ([observability.md](observability.md)). Iceberg/Trino catalog stays backlog **6**.

**Delivered:**

| # | Deliverable |
| --- | --- |
| 3a | **Image:** `openmetadata/{postgresql,server,ingestion}:2.0.3` + Elasticsearch `9.3.0` |
| 3b | **ClickHouse user:** `nexus_catalog` (SELECT/SHOW on `system.*` + bronze/silver/gold) via RBAC bootstrap |
| 3c | **Catalog ingest:** `./scripts/observability-ingest.sh openmetadata` (one-shot ingestion image; verifies `raw_route__products`, `stg_route__products`, `dim_product`) |
| 3d | **Lake dbt:** attaches `artifacts/dbt/dlt_dbt_clickhouse/{run_id}/` to service `nexus_clickhouse`; markers under `indexes/openmetadata/` |
| 3e | **Vault:** KV `openmetadata` + `clickhouse_catalog` → Agent; env defaults for local login |
| 3f | **Caddy:** `openmetadata.${NEXUS_PUBLIC_HOST}` (already wired) |
| 3g | Smoke/docs: [docker/openmetadata/README.md](../docker/openmetadata/README.md), observability/ops/vault/rbac |

**Done when:** `./scripts/start.sh openmetadata` is healthy **and** `observability-ingest.sh openmetadata` catalogs products tables from ClickHouse (+ lake dbt when present).

### 3.1 OpenMetadata ELT projection — done

OM is the **central catalog / DQ / governance hub**. dbt docs HTML, Elementary HTML, and OpenObserve remain deep-dive UIs; lake stays SoR; pipelines still do not call OM APIs. Future Iceberg/Databricks sources follow the same reader pattern (backlog **6+**).

| # | Deliverable |
| --- | --- |
| 3.1a | **dbt lineage:** sources use `schema: bronze_{env}` only (no layer `database`) so OM resolves `default.bronze_*` → silver → gold |
| 3.1b | **dbt TestCaseResults:** lake `run_results.json` (+ optional `sources.json`); manifest rewrite for older lake artifacts; `searchAcrossDatabases` |
| 3.1c | **Profiler + elementary schema:** catalog/profile `elementary_{env}`; `nexus_catalog` SELECT on elementary |
| 3.1d | **Airflow pipelines:** ingest `route_clickhouse_products` (dlt/dbt orchestration) via Airflow Postgres backend |
| 3.1e | **Deep-dive links:** CustomDashboard entries (`sourceUrl`) for Elementary + dbt docs + warehouse under `nexus_observability_links` (Caddy hostnames now; auth gate in item **9**) |

**Done when:** `--force` ingest shows bronze→silver lineage, `testCaseResults` > 0 (DQ dashboard), Airflow pipeline entity when Airflow is up, elementary schema visible, and CustomDashboard deep-dive links create/update with browser-reachable `sourceUrl`s.

### 4. MinIO IAM — done

Four IAM users + root for bootstrap. Usernames have no env suffix. Passwords are Vault KV (`minio_loader`, `minio_reader`, `minio_platform_reader`, `minio_admin`), rendered by Agent. Root remains the server and `minio-init` only. Polaris/Spark/Trino S3 use `nexus_loader`. Polaris **catalog** RBAC stays item **6**.

| # | Deliverable |
| --- | --- |
| 4a | Policies in `docker/minio/iam/` — loader on all five buckets (multipart; Delete deny on append-only archives + telemetry; Delete allow on Iceberg warehouse), reader markers, platform_reader all-buckets read-only, admin break-glass |
| 4b | `./scripts/minio-iam-bootstrap.sh` creates users from Vault and probes multipart, Iceberg write, platform_reader get/deny-put, reader markers |
| 4c | dlt, observability, OTel, Airflow logs, Polaris/Spark/Trino → `nexus_loader`. Lake replay → `nexus_reader`. Demo share → `nexus_platform_reader` |
| 4d | Log expiry (ILM) is **not** this item |

**Done when:** bootstrap probe passes on local MinIO with `NEXUS_SECRETS_BACKEND=vault`.

### 5. Local Terraform

Modules under `infrastructure/terraform/` against local endpoints. Hostinger DNS/edge and Actions stay in item **10**. HashiCorp Terraform only (BSL); no OpenTofu/Ansible.

**Known issue — dual ownership (resolve when implementing item 5):**

Today two paths create the same resource classes:

| Resource | Current owner |
| --- | --- |
| MinIO buckets | Compose `minio-init` → `docker/minio/init/create-buckets.sh` |
| MinIO IAM users + policies | `./scripts/minio-iam-bootstrap.sh` |
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

**Ops (optional, not ordered here):** MinIO REST archive → R2 via `./scripts/backup-archive.sh` and manual Vault snapshots — [operations.md](operations.md#archive-backup-optional--minio--r2), [vault.md](vault.md). Does **not** reorder or block item **5**.

### 11. Supabase + Streamlit

Supabase auth/session; Streamlit portfolio/control UI. Not pipeline telemetry storage.

### 12. RAG (later)

Multi-agent + RAG over `docs/` + semantic layer. Do not start before items 8 and 11 are in place.

---

## Explicit non-goals (until listed above)

- OpenTofu or Ansible
- Terraform as app deploy / Compose / `uv` updater
- Pipeline code calling SigNoz, OpenObserve, or OpenMetadata APIs
- LLM/RAG before semantic layer + Streamlit shell
- Speculative stubs that skip verification of the current backlog item
- Grafana stack (deferred until both branches + LLM are running)
