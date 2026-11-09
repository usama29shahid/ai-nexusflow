# Self-hosted Supabase (backlog item 11)

Website database: Auth, PostgREST, and pgvector. ClickHouse stays the warehouse. Qdrant is optional and is not used by this stack. Pipeline telemetry stays in the observability lake; Vector only ships Supabase container logs.

This file is the setup record for the self-hosted Supabase stack.

## What starts

`./scripts/start.sh` starts Supabase when `COMPOSE_PROFILES` in `.env` contains `supabase`. The same stack starts with:

```bash
./scripts/start.sh supabase
./scripts/start.sh stop-supabase
```

`supabase` is not a service in the root Compose file. `scripts/supabase-compose.sh` uses three files:

- `docker-compose.yml` — pinned upstream services (Postgres **17.6.1.136** is already the default)
- `docker-compose.kong.yml` — Kong **3.9.3** instead of Envoy
- `docker-compose.nexus.yml` — loopback ports, slim profile, Vector **0.53.0-alpine**

`docker-compose.pg15.yml` and `docker-compose.pg17.yml` are upstream image overrides. `start.sh` does not pass them. This lab was created on Postgres 17.

Slim services: `db`, `auth`, `rest`, Kong (`api-gw`), `meta`, `studio`, `vector`.

Left off: Realtime, Storage, imgproxy, Edge Functions, pooler, Logflare Analytics. Website files, when a UI needs them, go to MinIO (a bucket such as `nexus-app-{env}`), not Supabase Storage. The Studio Storage page fails because that service is not running. Leave the Studio ClickHouse wrapper off; ClickHouse is not a foreign table in this Postgres.

| Surface | Bind |
| --- | --- |
| API (Kong: Auth + PostgREST) | `http://127.0.0.1:8000` |
| Studio | `http://127.0.0.1:3001` |
| Postgres | not published; `docker exec` into `supabase-db` |

EC2 laptop tunnels for `3001` and `8000`: [docs/operations.md](../../docs/operations.md#ec2-laptop-ssh-tunnels-for-uis).

Compose project name: `nexus-supabase`. Containers join the external network `ai-nexusflow_default` so Vector can reach `otel-collector`.

`./scripts/start.sh supabase` warns when available RAM is under 2 GiB. It does not stop the stack. A normal `./scripts/start.sh` does not print that warning.

If Auth health on port 8000 never succeeds, `start.sh` exits and does not print the API URL as ready. On success it runs migrations and the role bootstrap, then the Ready line includes `supabase`.

## Secrets

| Secret | Where |
| --- | --- |
| API keys, JWT, Postgres password, Studio login | `.nexusflow/supabase.env` (mode 600, gitignored). First start copies `docker/supabase/.env.example` and runs `utils/generate-keys.sh` |
| Studio login | `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` in that file only. Vault does not render them |
| Process DB roles | `.nexusflow/supabase-rbac.env`, and Vault `secret/nexusflow/{env}/supabase_loader`, `supabase_reader`, `supabase_catalog`, `supabase_admin` |
| API keys for other processes | Vault `secret/nexusflow/{env}/supabase` (`publishable_key`, `secret_key`, `anon_key`, `service_role_key`, `jwt_secret`, `postgres_password`) |

`./scripts/vault-bootstrap.sh` creates those five paths when they are missing. It copies API keys from `.nexusflow/supabase.env` and role passwords from `.nexusflow/supabase-rbac.env` when the files already exist. If Vault ran first, fields can be empty until `./scripts/start.sh supabase` finishes and runs `./scripts/supabase-vault-sync.sh` (fills empty fields only, then recreates `vault-agent`). A field that already has a Vault value is left as it is. A failed read of an existing secret stops the write. `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_SECRET_KEY` stay empty until `utils/add-new-auth-keys.sh` writes them.

Canonical env file is `.nexusflow/supabase.env`. `docker/supabase/.env` must be a symlink to it. If both are regular files with different generated secrets, `supabase-ensure-env.sh` refuses to start until you keep one copy.

Auth container logs never forward GoTrue free-text `msg`/`error` (only level, path, status, and `error=present`) before Vector ships them to the lake / OpenObserve. Vector’s own API listen is disabled.

The browser may use the publishable / anon key. The service-role key and `nexus_admin` stay on the server.

Lab defaults written into `.nexusflow/supabase.env` on first create: `SUPABASE_PUBLIC_URL=http://127.0.0.1:8000`, `API_EXTERNAL_URL=http://127.0.0.1:8000/auth/v1`, `SITE_URL=http://127.0.0.1:3001`, `ENABLE_EMAIL_AUTOCONFIRM=true`. Autoconfirm is for this lab (no SMTP). Do not copy that flag onto a public host.

## Database

Migrations under `docker/supabase/migrations/` apply as `postgres` on each start. `schema_migrations` records the file name. Applied files are not run again.

| Migration | What it adds |
| --- | --- |
| `001_app_roles_profiles_pgvector` | `extensions.vector`, `profiles` (one row per Auth user, trigger on `auth.users`), `document_chunks.embedding vector(3)`, forced RLS, loader write policy |
| `002_reader_catalog_select_admin_bypassrls` | `SELECT` for `nexus_reader` and `nexus_catalog` on `profiles` and `document_chunks`; `nexus_admin` `BYPASSRLS` |
| `003_schema_migrations_rls` | Revoke API roles from `public.schema_migrations` and force RLS. `postgres` still records applied files |

`vector(3)` is the smoke size until an embedding model is chosen. A later migration changes the dimension. Distance is cosine (`<=>`). `match_document_chunks` is `security invoker` and is granted to `authenticated`.

| Role | Use |
| --- | --- |
| `anon` / `authenticated` | Supabase API roles. Logged-in users read their own profile and all chunks. They cannot insert chunks |
| `nexus_loader` | Embedding ingest. `INSERT` / `UPDATE` on `document_chunks` |
| `nexus_reader`, `nexus_catalog` | `SELECT` on `profiles` and `document_chunks` |
| `nexus_admin` | Break-glass. `BYPASSRLS` plus grants on `public` |
| `service_role` | Server bootstrap only. Not a browser key |

Postgres is not published on the host (nexus overlay). Connect as a process role inside the DB container, for example:

```bash
docker exec -it supabase-db psql -U postgres -d postgres
# or: docker exec -it supabase-db psql -U nexus_reader -d postgres
```

## Logs and backup

Two observability surfaces (do not merge them):

| Surface | What | Where |
| --- | --- | --- |
| Studio **Query Performance** / **Database Connections** | Postgres stats (`pg_stat_statements`, sessions) | Studio only — works without Logflare |
| Auth / API / PostgREST / DB **service logs** | Container stdout/stderr | OpenObserve via Vector → OTel Collector → MinIO `nexus-telemetry-{env}` |

**Env:** Compose always uses `.nexusflow/supabase.env` via a symlink at `docker/supabase/.env`. `./scripts/supabase-ensure-env.sh` repairs dual-file drift, refuses upstream placeholder secrets, and must succeed before start.

**Vector / docker.sock:** `supabase-vector` mounts the host Docker socket **read-only** so it can tail slim-stack container logs. That is required for `docker_logs`; do not publish Vector’s API port. On a hardened VPS, treat socket access as trusted-host only (backlog **10**).

Vector tails `supabase-kong` / `supabase-envoy`, `supabase-auth`, `supabase-rest`, `supabase-db`, `supabase-studio`, and `supabase-meta`, tags `service.name=supabase` and `supabase.component` (`auth`, `api-gw`, `rest`, `db`, `studio`, `meta`), and posts OTLP/HTTP protobuf to `http://otel-collector:4318/v1/logs`. Config: `volumes/logs/vector-otel.yml`. OpenObserve dashboard: **Supabase logs** (`./scripts/openobserve-bootstrap.sh`). Analytics / Logflare stays off.

**Coverage notes:** Auth signup/login and API gateway HTTP lines show as `auth` / `api-gw`. GoTrue JSON keeps `msg`/`path`/`status` only (`error` becomes attribute `present`); non-JSON auth lines are redacted before OTLP. Table and RPC traffic (`profiles`, `document_chunks`, `match_document_chunks`) appear as gateway paths plus Postgres `ERROR`/`WARNING`/`FATAL`/`PANIC` on `db` when something fails. Vector drops Postgres `LOG` (checkpoints) and `STATEMENT`/`HINT`/`CONTEXT`/`DETAIL` companions so full SQL/embeddings are not archived. PostgREST itself rarely logs successful requests. pgvector is not a separate logger — extension/SQL issues show under `db`. Studio SQL timing stays on Query Performance, not in OpenObserve. Config check: `uv run python tests/unit/scripts/test_supabase_self_host.py`.

```bash
./scripts/backup-supabase.sh
# → MinIO nexus-supabase-{env}/dumps/YYYY/MM/DD/supabase-{timestamp}.dump
# Airflow DAG ops_backup_supabase (daily; needs supabase-db + MinIO + MINIO_LOADER_*)
# Off-site R2: ./scripts/backup-archive.sh or DAG ops_backup_archive
```

`pg_dump -Fc` of database `postgres` into MinIO (local S3). No durable host path under `.nexusflow/backups/`. R2 gets the same keys when the archive mirror runs. Restore outline: [docs/operations.md](../../docs/operations.md#supabase-backup-optional--postgres--minio--r2).
