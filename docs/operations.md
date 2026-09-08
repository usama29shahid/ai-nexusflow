# Daily operations runbook

Quick reference when you forget start/stop steps. For first-time install see [setup.md](setup.md). For Vault details see [vault.md](vault.md).

---

## What runs where

| Kind | Compose profile | Services |
| --- | --- | --- |
| **Always** | *(none)* | MinIO, minio-init, otel-collector |
| **Branch — warehouse** | `clickhouse` | ClickHouse |
| **Branch — lakehouse** | `lakehouse` | Polaris, polaris-setup, Spark Thrift, Trino |
| **Platform** | `cloudbeaver` | CloudBeaver |
| **Platform** | `airflow` | Airflow (postgres, webserver, scheduler) — Phase 1 orchestration |
| **Platform** | `signoz` | SigNoz — pipeline trace reader |
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

SigNoz and OpenMetadata are on-demand. Stop them without tearing down the rest of the stack:

```bash
./scripts/start.sh stop-signoz          # revert OTel to lake-only export
./scripts/start.sh stop-openmetadata
./scripts/start.sh stop-observability   # both readers
```

MinIO and `otel-collector` stay running. When SigNoz stops, `start.sh` switches the collector back to `collector-config.yaml` (no forward to `signoz:4317`).

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

```bash
docker compose ps

curl http://localhost:8123/ping                    # ClickHouse → Ok.
curl http://localhost:8080/v1/info                 # Trino
curl http://127.0.0.1:8081/health                  # Airflow
curl "http://127.0.0.1:8200/v1/sys/health?sealedcode=200"   # Vault
curl --fail http://localhost:8182/q/health         # Polaris
```

| UI | URL |
| --- | --- |
| MinIO console | http://localhost:9001 |
| Trino | http://localhost:8080 |
| Spark UI | http://localhost:4040 |
| CloudBeaver | http://localhost:8978 |
| Airflow | http://127.0.0.1:8081 |
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

`--profile-target` must match the dbt `--target` / `NEXUS_ENV` that wrote the tables (`elementary_dev` / `elementary_prd` in profiles). For shared or non-local viewing, add `--disable-samples` so failed-test sample rows (possible PII) are not embedded in the HTML.

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

## Cheat sheet

```text
First time ever     →  ./scripts/setup.sh
Start all stacks    →  ./scripts/start.sh all
Start .env stacks   →  ./scripts/start.sh
Stop all            →  ./scripts/start.sh down
Stop SigNoz only    →  ./scripts/start.sh stop-signoz
Stop OM only        →  ./scripts/start.sh stop-openmetadata
Stop both readers   →  ./scripts/start.sh stop-observability
Lakehouse after up  →  ./scripts/start.sh ./scripts/lakehouse-restore.sh
Vault after reboot  →  ./scripts/start.sh vault
dlt smoke           →  ./scripts/start.sh smoke
Elementary report   →  uv sync --extra elementary; edr report --profile-target "$NEXUS_ENV" (see above)
```
