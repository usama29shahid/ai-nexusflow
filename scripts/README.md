# scripts

Host bootstrap. Python stays on the host; Docker runs infrastructure only.

**Runbook:** [docs/operations.md](../docs/operations.md) — start/stop all services, lakehouse restore, Vault reboot.

```bash
cp .env.example .env   # or paste your .env
./scripts/setup.sh     # first-time: Compose + uv sync (+ Vault if enabled)
```

## Daily start / stop

```bash
./scripts/start.sh all          # everything: MinIO, both branches, CloudBeaver, Airflow, Vault
./scripts/start.sh              # only COMPOSE_PROFILES from .env (+ Vault if enabled)
./scripts/start.sh down         # stop all (avoids "network still in use")
./scripts/start.sh vault        # Vault only (platform secrets)
./scripts/start.sh airflow      # Airflow only (platform; on-demand)
./scripts/start.sh smoke
./scripts/start.sh dbt debug --project-dir branches/dlt_dbt_clickhouse
./scripts/start.sh shell
```

| Kind | Profiles / services | Tied to a branch? |
| --- | --- | --- |
| Always | MinIO + otel-collector (no profile) | No — shared |
| Platform | `vault`, `airflow`, `cloudbeaver` | No |
| Branch | `clickhouse`, `lakehouse` | Yes — `dlt_dbt_clickhouse` / `dlt_dbt_spark_iceberg` |

Set branch stacks in `.env` `COMPOSE_PROFILES` (e.g. `clickhouse,lakehouse`). Do **not** put `vault` in `COMPOSE_PROFILES` only for secrets — use `NEXUS_SECRETS_BACKEND=vault`; `start.sh` starts Vault as platform infra.

`start.sh` sources `.env` for config. When `NEXUS_SECRETS_BACKEND=vault`, commands that need credentials call `vault-ensure.sh` then source `.nexusflow/secrets.env` (passwords never from `.env`). See [docs/vault.md](../docs/vault.md).

After `docker compose down` and bringing the **lakehouse** profile back up, Polaris forgets Iceberg table registrations (MinIO data is kept). Restore Trino access:

```bash
./scripts/start.sh ./scripts/lakehouse-restore.sh
# or:
set -a && source scripts/load-secrets.sh && set +a
./scripts/lakehouse-restore.sh
```

Uses `NEXUS_ENV` from `.env` for the Polaris catalog name (`nexus_${NEXUS_ENV}`). `./scripts/setup.sh` also re-registers the smoke table when `lakehouse` is in `COMPOSE_PROFILES`.

Trino can take about a minute after `up` before queries work. The restore script waits for that. `Trino server is still initializing` means wait, not that data is gone.
