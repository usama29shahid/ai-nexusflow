# scripts

Host bootstrap. Python stays on the host; Docker runs infrastructure only.

```bash
cp .env.example .env   # or paste your .env
./scripts/setup.sh
```

After `docker compose down` and bringing the **lakehouse** profile back up, Polaris forgets Iceberg table registrations (MinIO data is kept). Restore Trino access:

```bash
set -a && source .env && set +a
./scripts/lakehouse-restore.sh
```

Uses `NEXUS_ENV` from `.env` for the Polaris catalog name (`nexus_${NEXUS_ENV}`). `./scripts/setup.sh` also re-registers the smoke table when `lakehouse` is in `COMPOSE_PROFILES`.

Trino can take about a minute after `up` before queries work. The restore script waits for that. `Trino server is still initializing` means wait, not that data is gone.
