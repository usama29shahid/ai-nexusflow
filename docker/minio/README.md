# MinIO (AIStor Free)

Shared S3 object store (always-on Compose service `minio`). Bucket bootstrap: [init/README.md](init/README.md).

## License file (do not commit)

MinIO AIStor Free needs a license file. Put it here, next to other local secrets:

```text
.nexusflow/minio.license
```

That directory is gitignored (same as Vault’s `.nexusflow/secrets.env`). Do **not** put the file under `docker/minio/` or anywhere tracked.

```bash
mkdir -p .nexusflow
cp /path/to/downloaded-license .nexusflow/minio.license
chmod 600 .nexusflow/minio.license
```

The download may be named `minio.license` or `license.minio` — rename it to `.nexusflow/minio.license`.

Compose bind-mounts it read-only as `/minio.license`. **`./scripts/start.sh` and `./scripts/setup.sh` refuse to start** if that path is missing or is a directory. Bare `docker compose up` does **not** check. If the file is missing, Docker often creates a **directory** at `.nexusflow/minio.license` — `rmdir` it, then copy the real file (chmod 600). S3 stays blocked until the file is valid.

On the VPS, copy the **same path in that clone**. Vault Agent does **not** render this file today (only `MINIO_ROOT_*` and the IAM env vars). Do not commit the license; do not copy a WSL license into git. See [docs/vault.md](../../docs/vault.md).

## IAM verify

```bash
./scripts/minio-iam-bootstrap.sh          # apply + multipart probe
./scripts/minio-iam-service-check.sh      # loader/reader + OTel/Airflow/lakehouse wiring
```

## IAM users

`./scripts/minio-iam-bootstrap.sh` creates four IAM users from Vault.

**`mc` pin / upsert contract:** apply runs in
`MINIO_MC_IMAGE` (Compose default `quay.io/minio/aistor/mc:RELEASE.2026-09-06T02-44-40Z`,
same pin as `minio-init`). On that image, `mc admin policy create` and
`mc admin user add` **upsert** policy JSON and user secrets — `docker/minio/iam/apply.sh`
must not `policy remove` / `user remove`. If you change the `mc` pin, re-run
`./scripts/minio-iam-bootstrap.sh` and confirm upsert still works before relying on apply-only.

| User | Vault path | Use |
| --- | --- | --- |
| `nexus_loader` | `minio_loader` | Process writes (archive, telemetry, Airflow logs, Iceberg) + Polaris/Spark/Trino S3 |
| `nexus_reader` | `minio_reader` | Lake-replay scripts |
| `nexus_platform_reader` | `minio_platform_reader` | Demo share — all buckets read-only |
| `nexus_admin` | `minio_admin` | Break-glass |

Root still creates buckets in [init/create-buckets.sh](init/create-buckets.sh). Policies: [iam/](iam/). Contract: [docs/rbac.md](../../docs/rbac.md).
