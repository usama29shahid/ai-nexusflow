# Daily operations runbook

Quick reference when you forget start/stop steps. For first-time install see [setup.md](setup.md). For Vault details see [vault.md](vault.md).

---

## What runs where

| Kind | Compose profile | Services |
| --- | --- | --- |
| **Always** | *(none)* | MinIO AIStor Free, minio-init, otel-collector |
| **Branch — warehouse** | `clickhouse` | ClickHouse |
| **Branch — lakehouse** | `lakehouse` | Polaris, polaris-setup, Spark Thrift, Trino |
| **Platform** | `cloudbeaver` | CloudBeaver |
| **Platform** | `airflow` | Airflow (postgres, api-server, dag-processor, scheduler) — Phase 1 orchestration |
| **Platform** | `signoz` | SigNoz — pipeline trace reader (item 2) |
| **Platform** | `openobserve` | OpenObserve — primary observer under test (item **2.1**) |
| **Platform** | `openmetadata` | OpenMetadata — data catalog reader |
| **Platform** | `vault` | Vault, vault-agent (when `NEXUS_SECRETS_BACKEND=vault`) |

Vault is **not** a branch. `start.sh` starts it when secrets backend is `vault`.

**Observability (Phase 1):** MinIO bucket `nexus-telemetry-{env}` is the data lake. OTel Collector is always-on with MinIO (independent of branches). SigNoz and OpenMetadata are on-demand reader profiles. See [observability.md](observability.md).

---

## Start everything (all branches + platform tools)

From the repository root:

```bash
./scripts/start.sh all
```

This starts:

- MinIO (always)
- ClickHouse, Polaris, Spark, Trino (both branches)
- CloudBeaver, Airflow
- Vault + Agent (if `NEXUS_SECRETS_BACKEND=vault`)
- **Lakehouse restore** (re-register Polaris / Iceberg smoke — see below)

---

## Start only what `.env` says

If `COMPOSE_PROFILES` in `.env` lists your stacks (e.g. `clickhouse,lakehouse,cloudbeaver`):

```bash
./scripts/start.sh
```

Add Airflow separately if it is not in `COMPOSE_PROFILES`:

```bash
./scripts/start.sh airflow
```

---

## Stop everything

Plain `docker compose down` often leaves **profiled** services (Vault, Airflow, ClickHouse, lakehouse, CloudBeaver) running and prints `Network … still in use`.

Use one command — it enables every Compose profile on the way down:

```bash
./scripts/start.sh down
```

Do **not** use `down -v` unless you intend to **delete** MinIO / ClickHouse data volumes.

---

## Stop observability readers (keep MinIO + OTel + branches)

SigNoz, OpenObserve, and OpenMetadata are on-demand. Stop them without tearing down the rest of the stack:

```bash
./scripts/start.sh stop-signoz          # re-sync OTel exporters
./scripts/start.sh stop-openobserve     # re-sync OTel exporters
./scripts/start.sh stop-openmetadata
./scripts/start.sh stop-observability   # all three readers
```

MinIO and `otel-collector` stay running. When readers stop, `start.sh` re-renders collector exporters (lake always; remaining readers keep their forward).

---

## dlt / dbt (secrets loaded automatically)

```bash
./scripts/start.sh smoke          # ClickHouse dlt smoke
./scripts/start.sh dbt debug --project-dir branches/dlt_dbt_clickhouse
./scripts/start.sh shell          # shell with secrets exported
```

---

## Do I need `lakehouse-restore.sh` every time Docker restarts?

**No — not for every Docker restart.** Run it only when the **lakehouse stack was stopped and started again**.

| Situation | Run `./scripts/lakehouse-restore.sh`? |
| --- | --- |
| `./scripts/start.sh all` after `down` | **Yes** — `start.sh all` runs it for you |
| `./scripts/start.sh` and `lakehouse` is in profiles, after a previous `down` | **Yes** — run manually (see below) |
| `./scripts/setup.sh` with `lakehouse` in profiles | **Often yes** — setup tries smoke registration; use restore if Trino queries fail |
| Containers kept running (no `compose down`) | **No** |
| Only restarted ClickHouse / MinIO / Vault (lakehouse untouched) | **No** |
| WSL / PC reboot → you run `start.sh` again after `down` | **Yes**, if you use Trino / Spark / lakehouse dbt |

**Why:** Local Polaris uses an **in-memory catalog**. After `docker compose down` + `up`, catalog metadata is gone but **Iceberg files remain in MinIO**. Restore re-bootstraps Polaris and re-registers tables so Trino/Spark/dbt work again.

**Manual restore** (when not using `start.sh all`):

```bash
./scripts/start.sh ./scripts/lakehouse-restore.sh
```

Wait ~1 minute for Trino if the script says it is still initializing.

---

## Vault after VPS / container reboot

Vault seals on restart. Commands that need credentials (`smoke`, `dbt`, stack starts) run **`scripts/vault-ensure.sh`** (unseal + Agent if needed) then source `.nexusflow/secrets.env`. Infra-only stops skip Vault. Full bootstrap: `./scripts/start.sh vault`.

Vault only (no other stacks):

```bash
./scripts/start.sh vault
```

---

## Verify services

One command. It prints `PASS` / `FAIL` / `SKIP` and exits non-zero on any `FAIL`. It does not start or repair containers.

```bash
./scripts/start.sh verify
```

Start the stacks first. `./scripts/start.sh all` brings up MinIO, OTel, ClickHouse, lakehouse, CloudBeaver, and Airflow (plus Vault when `NEXUS_SECRETS_BACKEND=vault`). Readers stay on demand:

```bash
./scripts/start.sh openobserve     # primary UI under test (item 2.1); Vault/env ZO_ROOT_USER_*
./scripts/openobserve-bootstrap.sh # optional dashboards
./scripts/observability-ingest.sh openobserve
./scripts/start.sh signoz          # retained (item 2); sets JWT + OTLP ensure
./scripts/signoz-bootstrap.sh
./scripts/observability-ingest.sh signoz
./scripts/start.sh openmetadata    # catalog UI (item 3); 2.0.3 + ES 9
./scripts/clickhouse-rbac-bootstrap.sh   # ensures nexus_catalog
./scripts/observability-ingest.sh openmetadata
```

**OpenObserve:** UI `http://127.0.0.1:5080` — see [docker/openobserve/README.md](../docker/openobserve/README.md). Credentials from `.env` or Vault KV `openobserve`.

**SigNoz JWT:** Compose requires `SIGNOZ_TOKENIZER_JWT_SECRET`. Always use `./scripts/start.sh signoz`. See [docker/signoz/README.md](../docker/signoz/README.md).

**SigNoz ready check:** UI `http://127.0.0.1:3301` → Traces with `serviceName = nexusflow.dlt`; Dashboards → products / collector / uptime / ingestion.

`openmetadata-ingestion` is skipped on purpose (optional heavy OM Airflow; catalog ingest uses a one-shot image — see backlog item 3). Vault checks run only when `NEXUS_SECRETS_BACKEND=vault`, and they fail while Vault is sealed (`"sealed":false` is required). CloudBeaver and Caddy are checked when that profile is in `COMPOSE_PROFILES` or the container is already running.

One-shots that should be `Exited (0)`: `minio-init`, `airflow-init`, `openmetadata-migrate`. `polaris-setup` stays up.

Manual curls (same targets the script uses):

```bash
docker compose ps

curl http://localhost:8123/ping                    # ClickHouse → Ok.
curl -sf http://127.0.0.1:13133/                   # OTel collector health
curl http://localhost:8080/v1/info                 # Trino
curl http://127.0.0.1:8081/api/v2/monitor/health   # Airflow 3 api-server
curl -sf http://127.0.0.1:8200/v1/sys/health | grep -q '"sealed":false'   # Vault unsealed
curl --fail http://localhost:8182/q/health         # Polaris
curl -sf http://127.0.0.1:3301/api/v1/health       # SigNoz
curl -sf http://127.0.0.1:5080/healthz             # OpenObserve
curl -sf http://127.0.0.1:8586/healthcheck         # OpenMetadata admin
```

| UI | URL |
| --- | --- |
| MinIO console | http://localhost:9001 |
| Trino | http://localhost:8080 |
| Spark UI | http://localhost:4040 |
| CloudBeaver | http://localhost:8978 |
| Airflow | http://127.0.0.1:8081 |
| OpenObserve | http://127.0.0.1:5080 |
| SigNoz | http://127.0.0.1:3301 |
| OpenMetadata | http://127.0.0.1:8585 |
| Elementary (dbt DQ) | Local HTML via `edr report` (no Docker service) — see below |

### Elementary report (host CLI)

Needs ClickHouse up and an `elementary` profile (copy from [`profiles.example.yml`](../branches/dlt_dbt_clickhouse/profiles.example.yml) into branch `profiles.yml` or `~/.dbt/profiles.yml`).

Install once (intentional — this extra shares the project venv: Elementary pins `networkx` 2.x and the resolver may pick an older `boto3`/`botocore`/`aiobotocore` than a plain sync):

```bash
uv sync --extra elementary
```

Plain `./scripts/setup.sh` / `uv sync` does **not** install `edr`. After enabling the extra, keep using `uv sync --extra elementary` when refreshing the lock so report tooling stays installed. If you need the pre-extra AWS client pins, use a separate venv or omit the extra until you generate a report.

**Everyday refresh (after any `dbt run` / `dbt test` / `dbt build`):** the package `on-run-end` hook already wrote ClickHouse `elementary_{env}`. Regenerate the static HTML only:

```bash
./scripts/start.sh uv run edr report \
  --profiles-dir branches/dlt_dbt_clickhouse \
  --project-dir branches/dlt_dbt_clickhouse \
  --profile-target "$NEXUS_ENV" \
  --target-path edr_target \
  --open-browser false
# Open: edr_target/elementary_report.html (WSL: open the path in Windows browser)
```

`--profile-target` must match the dbt `--target` / `NEXUS_ENV` that wrote the tables (`elementary_dev` / `elementary_prd` in profiles). For shared or non-local viewing, add `--disable-samples true` so failed-test sample rows (possible PII) are not embedded in the HTML.

**First-time / empty index only** — build Elementary models, then run tests (or a normal project `dbt build`) so hooks populate history, then `edr report` as above:

```bash
./scripts/start.sh dbt run --select elementary --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV"
./scripts/start.sh dbt test --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV"
```

**Package upgrade (e.g. Elementary dbt package 0.19 → 0.25):** ClickHouse incremental tables may fail with `NUMBER_OF_COLUMNS_DOESNT_MATCH` because column layouts changed. Drop the broken table(s) in `elementary_{env}` first (or the whole DB if you can afford to lose DQ history), then deps + rebuild:

```bash
# Required when the table schema changed — example for one table:
# DROP TABLE IF EXISTS elementary_dev.test_result_rows;  -- via clickhouse-client / HTTP

./scripts/start.sh dbt deps --project-dir branches/dlt_dbt_clickhouse
./scripts/start.sh dbt run --select elementary --full-refresh --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV"
```

`--full-refresh` alone often does **not** fix a mismatched ClickHouse table; drop first, then re-run.

---

## Archive backup (optional — MinIO → R2)

Secondary copy of **REST JSONL history** only. Same bucket names and object keys on Cloudflare R2 (or any S3-compatible endpoint). Not a backlog item; does not replace item **5** (Terraform).

| Copied | Not copied |
| --- | --- |
| `nexus-dlt-dbt-clickhouse-{env}` | ClickHouse volumes (rebuild via load + dbt) |
| `nexus-dlt-dbt-spark-iceberg-archive-{env}` | Telemetry, Airflow logs, Iceberg warehouse, reader DBs |

**Config** — R2/S3 API keys in Vault KV `secret/nexusflow/{env}/backup` (Agent → `NEXUS_BACKUP_*`). Each machine’s Vault holds **that** host’s R2 URL/keys. See [vault.md](vault.md).

```bash
# One-time (or rotate): from a shell with Vault CLI / docker exec into vault
vault kv put secret/nexusflow/dev/backup \
  endpoint='https://<accountid>.r2.cloudflarestorage.com' \
  access_key='…' \
  secret_key='…'
./scripts/start.sh vault   # recreate Agent so secrets.env updates
```

Remove real `NEXUS_BACKUP_*` from `.env` after the KV path is set (bootstrap only seeds missing paths from `.env`).

**Run** (MinIO up; Vault Agent rendered for loader + backup keys):

```bash
./scripts/backup-archive.sh
```

**Airflow (daily):** DAG `ops_backup_archive` (`schedule` = every 24h). Needs Airflow profile up, MinIO up, and `NEXUS_BACKUP_*` in `.nexusflow/airflow_elt.env` (written by `./scripts/start.sh airflow` from Vault). After changing R2 keys in Vault, re-run `./scripts/start.sh airflow` so the elt env refreshes. Manual trigger from the Airflow UI anytime.

Uses `mc mirror` **without** `--remove`, so R2 keeps objects even if they disappear from local MinIO.

If the script fails with **Access Denied** on create: create both archive buckets in the **same** Cloudflare account as the token (exact names above), or use an R2 API token with **Admin Read & Write**. Object Read & Write is enough for mirror once buckets exist.

**Vault raft snapshots** (secrets themselves) stay a separate optional manual checklist — [vault.md](vault.md#backup-optional--good-to-have-not-required-for-local-day-to-day).

---

## On-demand restore

Assume wiped disk, `down -v`, or a new host. Goal: history back + stack usable.

### A — MinIO archive lost, R2 OK

1. Clone repo; Vault + `.env` (config only). Ensure `secret/nexusflow/{env}/backup` is set so Agent renders `NEXUS_BACKUP_*`.
2. `./scripts/start.sh minio` (empty archive buckets from minio-init).
3. Reverse mirror with Docker `mc` on the Compose network (same image as backup). Example for `NEXUS_ENV=dev`:

```bash
# After sourcing .env + scripts/load-secrets.sh and resolving the minio network:
# mc alias set local http://minio:9000 "$MINIO_LOADER_USER" "$MINIO_LOADER_PASSWORD"
# mc alias set backup "$NEXUS_BACKUP_ENDPOINT" "$NEXUS_BACKUP_ACCESS_KEY" "$NEXUS_BACKUP_SECRET_KEY"
# for b in nexus-dlt-dbt-clickhouse-dev nexus-dlt-dbt-spark-iceberg-archive-dev; do
#   mc mirror --overwrite "backup/${b}" "local/${b}"
# done
```

4. Confirm MinIO has `route/products/` prefixes (historical `run_id=` keys).

### B — Clean host / empty ClickHouse

1. Vault: unseal as usual (`./scripts/start.sh vault`) **or** Scenario C if secrets were lost.
2. Start stacks; `./scripts/clickhouse-rbac-bootstrap.sh` and `./scripts/minio-iam-bootstrap.sh` if fresh.
3. If archives empty: do **A** first.
4. For **current** warehouse tables: run Route `products` dlt + `dbt run` ([dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md)). Historical JSONL stays in the archive; full Bronze replay-from-archive is documented as a pattern but has **no dedicated script** yet.
5. Lakehouse Polaris reset only: `./scripts/lakehouse-restore.sh` (above).

### C — Vault lost; you have `.snap` + password-manager keys

1. Start Vault; unseal with the password-manager unseal key.
2. Restore raft snapshot ([HashiCorp restore](https://developer.hashicorp.com/vault/docs/commands/operator/raft#restore)); reload Agent.
3. Re-run MinIO IAM / ClickHouse RBAC bootstrap if needed.
4. Continue with A/B for data.

### D — No R2 and no MinIO

REST **history** is gone. You can only call the Route API again for the **current** catalog. Manual Vault backup does not recover JSONL.

---

## Cheat sheet

```text
First time ever     →  docs/setup.md (license + Airflow/SigNoz .env keys) then ./scripts/setup.sh
Start all stacks    →  ./scripts/start.sh all
Start .env stacks   →  ./scripts/start.sh
Stop all            →  ./scripts/start.sh down
Health check        →  ./scripts/start.sh verify   # does not start services
Stop SigNoz only    →  ./scripts/start.sh stop-signoz
Stop OpenObserve    →  ./scripts/start.sh stop-openobserve
Stop OM only        →  ./scripts/start.sh stop-openmetadata
Stop reader UIs     →  ./scripts/start.sh stop-observability
Lakehouse after up  →  ./scripts/start.sh ./scripts/lakehouse-restore.sh
Vault after reboot  →  ./scripts/start.sh vault
Archive → R2        →  ./scripts/backup-archive.sh  or Airflow DAG ops_backup_archive (daily)
dlt smoke           →  ./scripts/start.sh smoke
Airflow first time  →  orchestration/airflow/README.md (.env host path; once per machine)
Airflow             →  ./scripts/start.sh airflow  (UI :8081; recreate if key/.env changed)
Elementary report   →  uv sync --extra elementary; edr report --profile-target "$NEXUS_ENV" (see above)
Edge proxy (local)  →  ./scripts/proxy-hosts.sh install; ./scripts/start.sh proxy — docs/edge-proxy.md
```
