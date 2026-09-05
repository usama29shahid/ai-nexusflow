# Development setup

Same workflow on **WSL**, a **Hostinger VPS**, and **AWS EC2**: Linux + Docker Engine + uv.

> **Infrastructure is containerized. Python stays on the host.**

Secrets on the **Hostinger VPS** are stored in **HashiCorp Vault** and injected at runtime by Vault Agent — not as plaintext in `.env`. See [vault.md](vault.md). Local WSL may use `NEXUS_SECRETS_BACKEND=env` in `.env` until Vault is running. Engine RBAC is **held** (shared ClickHouse/MinIO users for now) — see [rbac.md](rbac.md).

Docker Compose runs **MinIO and OTel Collector always**, plus optional stacks via **profiles** (`clickhouse`, `lakehouse`, `cloudbeaver`, `airflow`). **Do not** run `uv sync` inside a Compose service that bind-mounts the repo — that created a root-owned `.venv` and `Permission denied (os error 13)`.

```text
git clone
cp .env.example .env          # or paste your .env
./scripts/setup.sh            # docker compose up -d && uv sync
```

| Component | Purpose | Where it runs |
| --- | --- | --- |
| Python, uv, DLT, dbt | App / ELT | Host |
| MinIO | Shared object store (no profile) | Docker |
| OTel Collector | Observability gateway → `nexus-telemetry-{env}` (always on) | Docker |
| SigNoz | Trace UI reader (`profile: signoz`) | Docker |
| OpenMetadata | Data catalog reader (`profile: openmetadata`) | Docker |
| ClickHouse | Warehouse (`profile: clickhouse`) | Docker |
| Polaris, Spark Thrift, Trino | Lakehouse (`profile: lakehouse`) | Docker |
| CloudBeaver | Web database IDE (`profile: cloudbeaver`) | Docker |
| Airflow | Orchestration (`profile: airflow`, Phase 1) | Docker |
| HashiCorp Vault | Secrets (`profile: vault` when `NEXUS_SECRETS_BACKEND=vault`) | Docker |

A later CI image for production Python is optional and does not change this Cursor/host workflow. See [architecture.md](architecture.md).

---

## One-command bootstrap

From the repository root:

```bash
cp .env.example .env
chmod +x scripts/setup.sh
./scripts/setup.sh
```

The script copies `.env` if missing, checks Docker, installs **uv** if missing, starts Compose (using `COMPOSE_PROFILES`, default `clickhouse`), and runs `uv sync` on the host. It does **not** apt-install Docker on WSL (use Docker Desktop WSL integration). On a bare VPS/EC2, install Docker Engine once, then re-run the script.

Day to day (deps unchanged):

```bash
./scripts/start.sh              # COMPOSE_PROFILES from .env
./scripts/start.sh all          # every stack — see docs/operations.md
./scripts/start.sh down         # stop everything cleanly
```

Full runbook: [operations.md](operations.md).

After `pyproject.toml` / `uv.lock` changes:

```bash
uv sync
```

---

## WSL extras

Windows 11 + WSL2 Ubuntu + Docker Desktop. Enable **Settings → Resources → WSL Integration → Ubuntu**.

```bash
docker --version
docker compose version
docker run hello-world
```

If `docker` is not found in WSL, integration is off.

---

## Environment variables

`.env` at the **repository root**. Do not commit it. Start from `.env.example`:

```env
NEXUS_ENV=dev
# NEXUS_RUN_ID=   # set per load; do not reuse one eternal value

# Which optional stacks to start. MinIO + otel-collector always run (not a profile).
# clickhouse | lakehouse | cloudbeaver | airflow — comma-separated for more than one.
# Airflow is on-demand: omit from the default, or: docker compose --profile airflow up -d
COMPOSE_PROFILES=clickhouse,lakehouse,cloudbeaver

CLICKHOUSE_HOST=localhost
CLICKHOUSE_DB=warehouse
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=change-me

CLICKHOUSE_HTTP_PORT=8123
CLICKHOUSE_NATIVE_PORT=9000

MINIO_API_PORT=9002
MINIO_CONSOLE_PORT=9001

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
```

On the **VPS**, move passwords and tokens into Vault KV (see [vault.md](vault.md)). Keep only configuration in `.env` when `NEXUS_SECRETS_BACKEND=vault`.

---

## Secrets (HashiCorp Vault)

Full standard: [vault.md](vault.md).

| Mode | `NEXUS_SECRETS_BACKEND` | Where secrets live |
| --- | --- | --- |
| Local WSL (default) | `env` | `.env` (gitignored) |
| Hostinger VPS (target) | `vault` | Vault KV v2 → Agent → `.nexusflow/secrets.env` |

Prefer `./scripts/start.sh` — it loads secrets, unseals Vault when needed, and starts Compose:

```bash
./scripts/start.sh              # COMPOSE_PROFILES from .env
./scripts/start.sh smoke
./scripts/start.sh dbt debug --project-dir branches/dlt_dbt_clickhouse
```

Or manually:

```bash
source scripts/load-secrets.sh
docker compose up -d
```

When `NEXUS_SECRETS_BACKEND=env`, `load-secrets.sh` sources `.env` only.

Never commit `.env`, Vault root token, unseal keys, or Agent credentials.

---

## Docker Compose

One file at the repo root. **Profiles name stacks**, not every container. MinIO has no profile so it always starts. Isolation between capabilities is buckets on that MinIO, not a second Compose project. Design: [architecture.md](architecture.md).

| Profile | Starts | Maps to |
| --- | --- | --- |
| *(none)* | MinIO, otel-collector | Shared object store + observability gateway |
| `clickhouse` | ClickHouse | `dlt_dbt_clickhouse` |
| `lakehouse` | Polaris, Spark Thrift, Trino | `dlt_dbt_spark_iceberg` |
| `cloudbeaver` | CloudBeaver web database IDE | Database administration and SQL exploration |
| `airflow` | Airflow (on-demand) | Orchestration; remote task logs in MinIO |

`COMPOSE_PROFILES` in `.env` is which **containers** run. `config/branches.yaml` is which **pipelines** may execute. Keep them aligned by hand.

```env
# Warehouse day
COMPOSE_PROFILES=clickhouse

# Lakehouse day
COMPOSE_PROFILES=lakehouse

# Both branches (default in .env.example)
COMPOSE_PROFILES=clickhouse,lakehouse

# Both branches plus the web database IDE
COMPOSE_PROFILES=clickhouse,lakehouse,cloudbeaver

# Orchestration day (Airflow UI + scheduler; add to any of the above)
COMPOSE_PROFILES=clickhouse,lakehouse,airflow
```

From the repo root:

```bash
docker compose up -d
docker compose ps
docker compose logs
docker compose logs clickhouse
docker compose config
docker compose --profile lakehouse up -d    # one-off; does not need .env change
docker compose --profile cloudbeaver up -d  # one-off; does not need .env change
docker compose --profile airflow up -d      # one-off profile; Airflow secrets must already be in .env
docker compose down          # keeps named volumes
# docker compose down -v     # deletes ClickHouse/MinIO data — avoid
```

Switching stacks: change `COMPOSE_PROFILES` and `docker compose up -d`. Do **not** use `down -v` to switch — that wipes MinIO buckets. `down` without `-v` stops containers and keeps `minio_data` / `clickhouse_data`.

If `.env` has no `COMPOSE_PROFILES`, a bare `docker compose up -d` starts **MinIO only**. `./scripts/setup.sh` defaults to `clickhouse` when the variable is unset.

There is no application `docker compose build` for Python. Images are pulled. The Airflow image includes the amazon provider used for MinIO remote task logging.

### Ports (from the host)

| Service | URL / port |
| --- | --- |
| ClickHouse HTTP | `localhost:8123` |
| ClickHouse native | `localhost:9000` |
| MinIO API | `localhost:9002` |
| MinIO console | `http://localhost:9001` |
| Polaris REST | `http://localhost:8181` |
| Spark Thrift (dbt-spark) | `localhost:10000` |
| Spark UI | `http://localhost:4040` |
| Trino UI | `http://localhost:8080` |
| CloudBeaver | `http://localhost:8978` |
| Airflow UI | `http://127.0.0.1:8081` |

From **another container**, use Compose DNS: `clickhouse:8123`, `minio:9000`, `polaris:8181`, `spark-thrift:10000`, `trino:8080` (MinIO listens on 9000 inside the network; the host maps API to 9002). CloudBeaver connects to ClickHouse at `clickhouse:8123` and Trino at `trino:8080`; do not use `localhost` for those connections inside CloudBeaver.

### Verify

```bash
curl http://localhost:8123/ping
```

Expected: `Ok.`

Open the MinIO console with credentials from `.env`.

**Lakehouse stack** (when `lakehouse` profile is active):

```bash
curl --fail http://localhost:8182/q/health          # Polaris management health
curl --fail http://localhost:8080/v1/info         # Trino
bash -c 'cat < /dev/null > /dev/tcp/localhost/10000' && echo "Spark Thrift OK"
```

Trino CLI (inside container): `docker exec -it trino trino --catalog nexus_dev`

CloudBeaver opens at `http://localhost:8978`. Its users, settings, and saved connections persist in the named `cloudbeaver_workspace` volume. Do not use `docker compose down -v` unless you intend to delete named volumes.

**Airflow** (when `airflow` profile is active):

```bash
curl --fail http://127.0.0.1:8081/health
```

UI login uses `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` (example default `admin` / `change-me`, local WSL only — change on shared hosts). `AIRFLOW__CORE__FERNET_KEY` and `AIRFLOW__WEBSERVER__SECRET_KEY` are required; `./scripts/setup.sh` generates them when blank. Trigger manual DAG `nexus_airflow_smoke` to verify the scheduler and MinIO remote task logs (`nexus-airflow-logs-dev`). Details: [orchestration/airflow/README.md](../orchestration/airflow/README.md).

---

## Python (uv)

Always from the **repository root** (not a nested `app/` folder):

```bash
uv sync
uv run python --version
uv run dlt --version
uv run dbt --version
```

Verified versions:

```text
Python          3.12.12
DLT             1.30.0
dbt-core        1.11.13
dbt-clickhouse  1.10.2
```

Warehouse Route `products` dlt is live (env = dbt `--target`; default `dev`). Warehouse vs lakehouse: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md). Route endpoints: [route-ingestion.md](route-ingestion.md). Prefer `unset NEXUS_RUN_ID` so the script mints a fresh id (leftover shell exports override minting).

```bash
set -a && source .env && set +a
export NEXUS_ENV=dev
unset NEXUS_RUN_ID
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4317}"
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py
# Optional explicit id (Airflow / replay / dlt→dbt chain):
# uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py --run-id local-20260905T120000Z
# After dbt models exist, pass the same run_id as var('run_id'):
# export NEXUS_RUN_ID=…   # from the products.py print line, or --run-id
# uv run dbt run --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
#   --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
# uv run dbt test --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV"
```

Lakehouse (Milestone 2, Spark Thrift required): `--project-dir branches/dlt_dbt_spark_iceberg` and `branches/dlt_dbt_spark_iceberg/dlt/route/products.py`.

dbt uses `~/.dbt/profiles.yml` unless you pass `--profiles-dir`. Profile names match Compose stacks: **`nexus_clickhouse`**, **`nexus_lakehouse`**. Passwords and hosts come from **environment variables only** (never hardcode secrets in `profiles.yml`).

dbt does **not** load the repo `.env`. Source config and secrets before every dbt command:

```bash
# VPS (after Vault): source scripts/load-secrets.sh
set -a && source .env && set +a
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse
uv run dbt debug --project-dir branches/dlt_dbt_spark_iceberg
```

On the VPS with Vault, use `scripts/load-secrets.sh` instead of sourcing `.env` alone. See [vault.md](vault.md).

Optional project copy: `profiles.example.yml` → `profiles.yml` in the branch folder (gitignored). Do not commit `profiles.yml`.

---

## Git

**Commit:** `pyproject.toml`, `uv.lock`, `docker-compose.yml`, `.env.example`, `.gitignore`, Python, dbt, docs, skeleton READMEs.

**Do not commit:** `.env`, `.venv/`, `__pycache__/`, dbt `logs/` / `target/`, secrets.

---

## Troubleshooting

### `.venv` Permission denied

**Cause:** Compose previously mounted the project and ran `uv sync` as root.

**Fix:** remove the host `.venv` and sync again as your user:

```bash
rm -rf .venv
uv sync
```

Do not mix Docker/root and host ownership of the same `.venv`.

### Docker not found in WSL

Enable Docker Desktop WSL integration for Ubuntu.

### Old `app/` path

`pyproject.toml` and dbt used to live under `app/`. They are now at the repo root and `branches/dlt_dbt_clickhouse`. Delete any leftover `app/.venv` if you still have one.
