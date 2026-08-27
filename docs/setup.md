# Development setup

Same workflow on **WSL**, a **Hostinger VPS**, and **AWS EC2**: Linux + Docker Engine + uv.

> **Infrastructure is containerized. Python stays on the host.**

Docker Compose runs **MinIO always**, plus optional stacks via **profiles** (`clickhouse`, `lakehouse`, `cloudbeaver`, and later `airflow`). **Do not** run `uv sync` inside a Compose service that bind-mounts the repo — that created a root-owned `.venv` and `Permission denied (os error 13)`.

```text
git clone
cp .env.example .env          # or paste your .env
./scripts/setup.sh            # docker compose up -d && uv sync
```

| Component | Purpose | Where it runs |
| --- | --- | --- |
| Python, uv, DLT, dbt | App / ELT | Host |
| MinIO | Shared object store (no profile) | Docker |
| ClickHouse | Warehouse (`profile: clickhouse`) | Docker |
| Polaris, Spark Thrift, Trino | Lakehouse (`profile: lakehouse`) | Docker |
| CloudBeaver | Web database IDE (`profile: cloudbeaver`) | Docker |
| Airflow, Kafka (later) | `airflow` / `kafka` profiles | Docker |

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
docker compose up -d          # uses COMPOSE_PROFILES from .env
```

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

# Which optional stacks to start. MinIO always runs (not a profile).
# clickhouse | lakehouse | cloudbeaver | airflow — comma-separated for more than one.
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

---

## Docker Compose

One file at the repo root. **Profiles name stacks**, not every container. MinIO has no profile so it always starts. Isolation between capabilities is buckets on that MinIO, not a second Compose project. Design: [architecture.md](architecture.md).

| Profile | Starts | Maps to |
| --- | --- | --- |
| *(none)* | MinIO | Shared object store |
| `clickhouse` | ClickHouse | `dlt_dbt_clickhouse` |
| `lakehouse` | Polaris, Spark Thrift, Trino | `dlt_dbt_spark_iceberg` |
| `cloudbeaver` | CloudBeaver web database IDE | Database administration and SQL exploration |
| `airflow` | Airflow (Phase 2) | Orchestration |

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
docker compose down          # keeps named volumes
# docker compose down -v     # deletes ClickHouse/MinIO data — avoid
```

Switching stacks: change `COMPOSE_PROFILES` and `docker compose up -d`. Do **not** use `down -v` to switch — that wipes MinIO buckets. `down` without `-v` stops containers and keeps `minio_data` / `clickhouse_data`.

If `.env` has no `COMPOSE_PROFILES`, a bare `docker compose up -d` starts **MinIO only**. `./scripts/setup.sh` defaults to `clickhouse` when the variable is unset.

There is no application `docker compose build` for Python. Images are pulled.

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

When ingestion exists (env = dbt `--target`; default `dev`). Warehouse vs lakehouse: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md). GitHub endpoints: [github-ingestion.md](github-ingestion.md).

```bash
export NEXUS_ENV=dev
export NEXUS_RUN_ID=local-$(date -u +%Y%m%dT%H%M%SZ)
uv run python branches/dlt_dbt_clickhouse/dlt/github/pull_requests.py
uv run dbt run --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
  --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
uv run dbt test --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV"
```

Lakehouse (Milestone 2, Spark Thrift required): `--project-dir branches/dlt_dbt_spark_iceberg` and `branches/dlt_dbt_spark_iceberg/dlt/github/pull_requests.py`.

dbt uses `~/.dbt/profiles.yml` unless you pass `--profiles-dir`. Profile names match Compose stacks: **`nexus_clickhouse`**, **`nexus_lakehouse`**. Passwords and hosts come from **environment variables only** (never hardcode secrets in `profiles.yml`).

dbt does **not** load the repo `.env`. Source it before every dbt command:

```bash
set -a && source .env && set +a
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse
uv run dbt debug --project-dir branches/dlt_dbt_spark_iceberg
```

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
