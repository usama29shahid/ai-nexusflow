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

On the VPS, copy the **same path in that clone**. Vault Agent does **not** render this file today (only `MINIO_ROOT_*` env vars). Do not commit the license; do not copy a WSL license into git. See [docs/vault.md](../../docs/vault.md).
