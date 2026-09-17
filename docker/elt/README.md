# ELT job image (`nexus-elt`)

Ephemeral Python image for Airflow tasks: `uv` venv with dlt, dbt-clickhouse, Elementary (`edr`).

Airflow stays thin and starts one container per task on the Compose network. Do **not** install these deps into the Airflow image.

```text
Airflow scheduler
  → docker run --rm --network ai-nexusflow_default nexus-elt:…
       → ./scripts/… or uv run python branches/…
```

## Build

```bash
./scripts/start.sh airflow
# or:
docker build -f docker/elt/Dockerfile -t nexus-elt:latest .
```

Rebuild after `uv.lock` / `pyproject.toml` changes. Editing SQL or dlt scripts does **not** require a rebuild (repo is bind-mounted at `/workspace`).

## Runtime contract

| Item | Value |
| --- | --- |
| Workdir | `/workspace` (host `NEXUS_REPO_ROOT` mount) |
| Venv | `/opt/nexus/.venv` via `UV_PROJECT_ENVIRONMENT` |
| Network | Compose project network (`clickhouse`, `minio:9000`, `otel-collector:4317`) |
| Secrets | `--env-file` from `.nexusflow/airflow_elt.env` (written by `./scripts/start.sh airflow`; rewrite after Vault password rotation) |

Cursor / manual runs stay on the host: `./scripts/start.sh uv run …`.
