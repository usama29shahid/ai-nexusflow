# Development setup

Same workflow on **WSL**, a **Hostinger VPS**, and **AWS EC2**: Linux + Docker Engine + uv.

> **Infrastructure is containerized. Python stays on the host.**

Docker Compose runs ClickHouse, MinIO, and later Spark/Iceberg, Airflow, Kafka. **Do not** run `uv sync` inside a Compose service that bind-mounts the repo — that created a root-owned `.venv` and `Permission denied (os error 13)`.

```text
git clone
cp .env.example .env          # or paste your .env
./scripts/setup.sh            # docker compose up -d && uv sync
```

| Component | Purpose | Where it runs |
| --- | --- | --- |
| Python, uv, DLT, dbt | App / ELT | Host |
| ClickHouse, MinIO | Warehouse, object store | Docker |
| Spark / Iceberg (later) | Branch 2 | Docker |
| Airflow, Kafka (later) | Orchestration, streaming | Docker |

A later CI image for production Python is optional and does not change this Cursor/host workflow. See [architecture.md](architecture.md).

---

## One-command bootstrap

From the repository root:

```bash
cp .env.example .env
chmod +x scripts/setup.sh
./scripts/setup.sh
```

The script copies `.env` if missing, checks Docker, installs **uv** if missing, starts Compose, and runs `uv sync` on the host. It does **not** apt-install Docker on WSL (use Docker Desktop WSL integration). On a bare VPS/EC2, install Docker Engine once, then re-run the script.

Day to day (deps unchanged):

```bash
docker compose up -d
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
CLICKHOUSE_DB=warehouse
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=

CLICKHOUSE_HTTP_PORT=8123
CLICKHOUSE_NATIVE_PORT=9000

MINIO_API_PORT=9002
MINIO_CONSOLE_PORT=9001

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
```

---

## Docker Compose

From the repo root:

```bash
docker compose up -d
docker compose ps
docker compose logs
docker compose logs clickhouse
docker compose config
docker compose down          # keeps named volumes
# docker compose down -v     # deletes ClickHouse/MinIO data — avoid
```

There is no application `docker compose build` for Python. Images are pulled.

### Ports (from the host)

| Service | URL / port |
| --- | --- |
| ClickHouse HTTP | `localhost:8123` |
| ClickHouse native | `localhost:9000` |
| MinIO API | `localhost:9002` |
| MinIO console | `http://localhost:9001` |

From **another container**, use Compose DNS: `clickhouse:8123`, `minio:9000` (MinIO listens on 9000 inside the network; the host maps API to 9002).

### Verify

```bash
curl http://localhost:8123/ping
```

Expected: `Ok.`

Open the MinIO console with credentials from `.env`.

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

When ingestion exists:

```bash
uv run python ingestion/dlt/pipelines/<pipeline>.py
uv run dbt run --project-dir branches/dlt_dbt_clickhouse
uv run dbt test --project-dir branches/dlt_dbt_clickhouse
```

dbt uses `~/.dbt/profiles.yml` unless you pass `--profiles-dir`. Optional project copy: `profiles.example.yml` → `profiles.yml` in this folder (gitignored). Do not commit `profiles.yml`.

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
