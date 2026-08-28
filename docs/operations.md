# Daily operations runbook

Quick reference when you forget start/stop steps. For first-time install see [setup.md](setup.md). For Vault details see [vault.md](vault.md).

---

## What runs where

| Kind | Compose profile | Services |
| --- | --- | --- |
| **Always** | *(none)* | MinIO, minio-init |
| **Branch — warehouse** | `clickhouse` | ClickHouse |
| **Branch — lakehouse** | `lakehouse` | Polaris, polaris-setup, Spark Thrift, Trino |
| **Platform** | `cloudbeaver` | CloudBeaver |
| **Platform** | `airflow` | Airflow (postgres, webserver, scheduler) |
| **Platform** | `vault` | Vault, vault-agent (when `NEXUS_SECRETS_BACKEND=vault`) |

Vault is **not** a branch. `start.sh` starts it when secrets backend is `vault`.

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

Vault seals on restart. **`./scripts/start.sh`** (including `smoke`, `dbt`, and `all`) unseals Vault and refreshes `.nexusflow/secrets.env` when `NEXUS_SECRETS_BACKEND=vault`.

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

---

## Cheat sheet

```text
First time ever     →  ./scripts/setup.sh
Start all stacks    →  ./scripts/start.sh all
Start .env stacks   →  ./scripts/start.sh
Stop all            →  ./scripts/start.sh down
Lakehouse after up  →  ./scripts/start.sh ./scripts/lakehouse-restore.sh
Vault after reboot  →  ./scripts/start.sh vault
dlt smoke           →  ./scripts/start.sh smoke
```
