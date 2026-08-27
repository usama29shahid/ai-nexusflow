# Airflow

On-demand orchestration for enabled branches. Not a data branch.

## Start (when needed)

Fernet key, web secret, and admin password must be set in `.env` first (Compose fails if they are blank). From a fresh `.env.example` copy, run `./scripts/setup.sh` once — it fills missing Airflow secrets — or generate them manually (see `.env.example`).

```bash
# One-off profile start (after secrets exist in .env)
docker compose --profile airflow up -d

# Or add airflow to COMPOSE_PROFILES, then:
docker compose up -d
```

| | |
| --- | --- |
| UI | http://127.0.0.1:8081 |
| Login | `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` (example default `admin` / `change-me`, **local WSL only**) |
| Remote logs | MinIO bucket `nexus-airflow-logs-{NEXUS_ENV}` |
| DAGs | `orchestration/airflow/dags/` (host-owned; add files as your Linux user) |
| Plugins | `orchestration/airflow/plugins/` |

`AIRFLOW__CORE__FERNET_KEY` and `AIRFLOW__WEBSERVER__SECRET_KEY` must be set in `.env` (Compose fails if empty). Leave them blank in `.env.example`; `./scripts/setup.sh` generates unique values. Do not commit real keys. Change `AIRFLOW_ADMIN_PASSWORD` before any shared host or VPS.

`airflow-init` only adjusts ownership of the **logs** named volume. It does **not** `chown` `dags/` or `plugins/` bind mounts — those stay writable by the host user for future source/branch ELT DAGs.

Set `AIRFLOW_UID` to your host UID (`id -u`, often `1000`) in `.env` so the webserver/scheduler match your account for any container-side file access.

Stop the profile stack (keeps volumes):

```bash
docker compose --profile airflow stop
```

## Smoke test

1. Open the UI and unpause `nexus_airflow_smoke` if needed.
2. Trigger a DAG run.
3. Confirm task `hello_nexus` succeeds and task logs appear (local volume + MinIO remote logging).

## Not in this slice

- Host dlt/dbt execution bridge (Python stays on the host; no `.venv` bind-mount)
- Source ELT DAGs / `config/branches.yaml` gating

See [docs/setup.md](../../docs/setup.md) and [docs/observability.md](../../docs/observability.md).
