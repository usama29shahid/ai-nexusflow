# Airflow

On-demand orchestration for enabled capabilities. Not a data branch.

Airflow runs in Docker (same Compose profile on WSL and VPS). Endpoint DAGs start an ephemeral **`nexus-elt`** container (`docker run` on the Compose network) that runs the same scripts as a manual host `uv` run. They do not bind-mount the developer `.venv` and do not SSH to the host.

## Runtime (locked)

| Now | Never |
| --- | --- |
| Thin Airflow + ephemeral ELT job image ([docker/elt/](../../docker/elt/)) | Install dlt/dbt into the Airflow image; standing dlt/dbt services; SSH host-exec for new DAGs |

Helper: [`dags/nexus_elt_exec.py`](dags/nexus_elt_exec.py). Copy `route_clickhouse_products` for the next endpoint. One UI lists every branch’s DAGs. Contract: [docs/architecture.md](../../docs/architecture.md).

## First time on this machine (WSL or VPS)

Do these once per machine (clone path / Linux user). Same list on the first VPS deploy.

1. **`.env` ELT vars** — Compose does **not** expand `$(pwd)`. Use the absolute clone path:

   ```bash
   NEXUS_REPO_ROOT=/home/india/projects/ai-nexusflow
   ```

   Optional: `DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)`, `NEXUS_ELT_IMAGE=nexus-elt:latest`, `NEXUS_COMPOSE_NETWORK=ai-nexusflow_default`.

2. **Docker socket** — only **`airflow-scheduler`** mounts `/var/run/docker.sock` (LocalExecutor runs ELT tasks there). The api-server does **not** get the socket, so a public `airflow.` UI later has a smaller blast radius. Your host user must still be able to run `docker` (Docker Desktop WSL or `docker` group on a VPS). Set `DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)` if tasks cannot talk to the daemon.

3. **Elementary CLI in the job image** — included via `uv sync --extra elementary` inside `docker/elt/Dockerfile`. No host `uv sync --extra elementary` required for Airflow tasks (still useful for local `edr report`).

4. **Start Airflow when you want the UI** (not one-time):

   ```bash
   ./scripts/start.sh airflow
   ```

   Builds `nexus-elt` and `nexus-airflow` (Airflow **3.3.2**), writes `.nexusflow/airflow_elt.env`, and starts the profile. Recreate with the same command after Vault password rotation so the host rewrites `airflow_elt.env` (the scheduler mounts only that file, not all of `.nexusflow`).

Fernet key, web/API secret, JWT secret, and admin password must already be in `.env` (`./scripts/setup.sh` once on a new clone; `./scripts/start.sh airflow` also fills a missing JWT). Change `AIRFLOW_ADMIN_PASSWORD` on a VPS.

**Upgrading from Airflow 2.x:** `./scripts/start.sh airflow` removes a leftover `airflow-webserver` container (frees `:8081`). Do not pass Compose `--remove-orphans` on the airflow profile — other stacks (ClickHouse, Vault) can look like orphans. Wipe the metadata volume (`docker volume rm ai-nexusflow_airflow_postgres_data`) so 3.x can migrate; warehouse/MinIO data stay. With Vault, the same command patches missing `jwt_secret` (via `vault-ensure.sh`) and recreates the Agent so `secrets.env` has JWT before Compose starts.

Compose project name follows the repo directory (default network `ai-nexusflow_default`). `start.sh` can detect the network; override with `NEXUS_COMPOSE_NETWORK` only if you renamed the project.

## Start / stop

```bash
./scripts/start.sh airflow
docker compose --profile airflow stop
```

`start.sh airflow` builds `docker/airflow/Dockerfile` (official image + docker CLI) and `docker/elt/Dockerfile`, and exits if `NEXUS_REPO_ROOT` or the Docker socket is missing. Do not start with bare `docker compose --profile airflow up` — Compose bind-mounts `.nexusflow/airflow_elt.env`, which only `start.sh` creates.

| | |
| --- | --- |
| UI | http://127.0.0.1:8081 (`airflow-api-server`) |
| Login | `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` (example default `admin` / `change-me`, **local WSL only**) |
| Config UI | Off (`AIRFLOW__API__EXPOSE_CONFIG=false`) — do not turn on behind a public hostname |
| Remote logs | MinIO bucket `nexus-airflow-logs-{NEXUS_ENV}` |
| DAGs | `orchestration/airflow/dags/` (host-owned) |
| Plugins | `orchestration/airflow/plugins/` |
| ELT image | `nexus-elt:latest` |

`airflow-init` only adjusts ownership of the **logs** named volume. Set `AIRFLOW_UID` to your host UID (`id -u`) in `.env`.

## DAGs

| DAG | Purpose |
| --- | --- |
| `nexus_airflow_smoke` | In-container smoke (no ELT image) |
| `route_clickhouse_products` | Route `/products` → Bronze → silver → gold → observability |

Grain: **one DAG per source + target + endpoint**. Tasks: `assert_branch_enabled` → `bronze` → `silver` (`dbt run` then `dbt test`) → `gold` (same) → `observability`. `observability_failed` runs on `one_failed` and writes the lake closer with `airflow.dag.failed`. Never `dbt build`. `NEXUS_RUN_ID` is the Airflow `run_id` (keep it free of `'` — `nexus_elt_exec` passes it via shell-single-quoted `-e`).

Unpause the DAG, trigger it, confirm the three Bronze tables share that `run_id` and lake objects exist under `nexus-telemetry-{env}`.

See [docs/setup.md](../../docs/setup.md) and [docs/observability.md](../../docs/observability.md).
