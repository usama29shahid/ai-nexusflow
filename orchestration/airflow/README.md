# Airflow

On-demand orchestration for enabled capabilities. Not a data branch.

Airflow runs in Docker (same Compose profile on WSL and VPS). dlt/dbt/`uv` stay on the **host**. Endpoint DAGs SSH to the Docker host and run `./scripts/start.sh` — they do not bind-mount `.venv`.

## First time on this machine (WSL or VPS)

Do these once per machine (clone path / Linux user). Same list on the first VPS deploy.

1. **`.env` host-exec vars** — Compose does **not** expand `$(id -un)`. Use the real login name and the absolute clone path:

   ```bash
   NEXUS_HOST_USER=india
   NEXUS_REPO_ROOT=/home/india/projects/ai-nexusflow
   ```

   On a VPS, change both to that server’s user and clone path. Optional: `NEXUS_HOST=host.docker.internal`, `NEXUS_HOST_PORT=22`.

2. **sshd** — tasks connect to port 22. A VPS usually already has this. WSL often does not:

   ```bash
   sudo apt-get install -y openssh-server
   sudo service ssh start
   ```

   After a WSL reboot, start sshd again if it is not enabled as a service (`sudo service ssh start`). Do not re-run the key script for that.

3. **SSH key** (once per machine):

   ```bash
   ./scripts/airflow-host-ssh-setup.sh
   ```

   Creates `.nexusflow/airflow_ssh/id_ed25519` and writes a **restricted** `authorized_keys` line: `command=` [`scripts/airflow-host-ssh-command.sh`](../../scripts/airflow-host-ssh-command.sh) (only this repo’s `./scripts/start.sh` allowlist) plus `from=` private Docker/RFC1918 ranges so a leaked key is not an internet login. Re-run after pulling this change so an older unrestricted line is replaced. Re-run also if the key, user, or machine changes. The key path must be a **file**, not a directory (if Compose started before the key existed, remove the path, run this script, then recreate Airflow). If SSH fails after restrict, set `NEXUS_AIRFLOW_SSH_FROM` to the Docker source CIDR and re-run the script.

4. **Elementary CLI** (once, or after `uv lock` refresh) — not a DAG task; the `observability` task runs `edr report`:

   ```bash
   uv sync --extra elementary
   ```

`./scripts/start.sh` prepends `$HOME/.local/bin` so `uv` is found over SSH (login PATH is not loaded).

5. **Start Airflow when you want the UI** (not one-time):

   ```bash
   ./scripts/start.sh airflow
   ```

   If Airflow was already running **before** the key or `.env` host-exec vars existed, recreate it with the same command so containers pick up the key mount, `openssh-client` image, and env.

Fernet key, web secret, and admin password must already be in `.env` (`./scripts/setup.sh` once on a new clone). Change `AIRFLOW_ADMIN_PASSWORD` on a VPS.

## Start / stop

```bash
./scripts/start.sh airflow
docker compose --profile airflow stop
```

`start.sh airflow` builds `docker/airflow/Dockerfile` (official image + `openssh-client`) and exits if the host SSH key file is missing.

| | |
| --- | --- |
| UI | http://127.0.0.1:8081 |
| Login | `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` (example default `admin` / `change-me`, **local WSL only**) |
| Config UI | Off (`AIRFLOW__WEBSERVER__EXPOSE_CONFIG=false`) — do not turn on behind a public hostname |
| Remote logs | MinIO bucket `nexus-airflow-logs-{NEXUS_ENV}` |
| DAGs | `orchestration/airflow/dags/` (host-owned) |
| Plugins | `orchestration/airflow/plugins/` |

`airflow-init` only adjusts ownership of the **logs** named volume. Set `AIRFLOW_UID` to your host UID (`id -u`) in `.env`.

## DAGs

| DAG | Purpose |
| --- | --- |
| `nexus_airflow_smoke` | In-container smoke (no host `uv`) |
| `route_clickhouse_products` | Route `/products` → Bronze → silver → gold → observability |

Grain: **one DAG per source + target + endpoint**. Tasks: `assert_branch_enabled` → `bronze` → `silver` (`dbt run` then `dbt test`) → `gold` (same) → `observability`. `observability_failed` runs on `one_failed` and writes the lake closer with `airflow.dag.failed`. Never `dbt build`. `NEXUS_RUN_ID` is the Airflow `run_id`.

Unpause the DAG, trigger it, confirm the three Bronze tables share that `run_id` and lake objects exist under `nexus-telemetry-{env}`.

See [docs/setup.md](../../docs/setup.md) and [docs/observability.md](../../docs/observability.md).
