# Development setup

Same workflow on **WSL**, a **Hostinger VPS**, and **AWS EC2**: Linux + Docker Engine + uv.

> **Infrastructure is containerized. Python stays on the host for Cursor.**

Airflow is Dockerized; DAG tasks run an ephemeral **`nexus-elt`** job container (`docker run` on the Compose network) with the same scripts as a manual `uv` run. Do **not** install dlt/dbt into the Airflow image. Locked decision: [architecture.md](architecture.md) (Airflow execution runtime), [orchestration/airflow/README.md](../orchestration/airflow/README.md).

Secrets are stored in **HashiCorp Vault** and injected at runtime by Vault Agent — not as plaintext in `.env`. See [vault.md](vault.md). **`NEXUS_SECRETS_BACKEND=vault` is required** for MinIO writers (OTel, dlt archive, Airflow logs, lakehouse S3): IAM passwords are Vault-only. `./scripts/start.sh` / `./scripts/setup.sh` refuse `env` for those paths and apply MinIO IAM after MinIO is up. ClickHouse RBAC and MinIO IAM (`nexus_loader` / `nexus_reader` / `nexus_platform_reader` / `nexus_admin`) — bootstrap via `./scripts/clickhouse-rbac-bootstrap.sh` and `./scripts/minio-iam-bootstrap.sh`. See [rbac.md](rbac.md), [backlog.md](backlog.md).

Docker Compose runs **MinIO AIStor Free and OTel Collector always**, plus optional stacks via **profiles** (`clickhouse`, `lakehouse`, `cloudbeaver`, `airflow`). Copy the Free license to `.nexusflow/minio.license` before the first start ([docker/minio/README.md](../docker/minio/README.md)). **Do not** run `uv sync` inside a Compose service that bind-mounts the repo — that created a root-owned `.venv` and `Permission denied (os error 13)`. On a **16 GB / 4-core** VPS, keep profiles strict (ClickHouse + Airflow day-to-day); do not start every stack at once.

```text
git clone
cp .env.example .env          # or paste a host-local .env — never copy another machine's .env
mkdir -p .nexusflow
cp /path/to/aistor-license .nexusflow/minio.license   # gitignored file (not a directory)
# Fill Compose-interpolation secrets in .env (see Before first setup.sh below)
./scripts/setup.sh            # docker compose up -d && uv sync
```

### Before first `./scripts/setup.sh` (WSL / EC2 / VPS)

Three things fail a clean host if skipped. License is always manual. Airflow and SigNoz values are required for **Compose file parse** even when those profiles are **off** — Docker Compose evaluates `${VAR:?…}` on included services before Vault starts. Filling them does **not** start Airflow or SigNoz.

| # | Required | Why |
| --- | --- | --- |
| 1 | `.nexusflow/minio.license` as a **file** | AIStor Free license is gitignored; `setup.sh` only checks that it exists. Create `mkdir -p .nexusflow`, then copy the license. If Docker once mounted a missing path, the path may be a **directory** — remove it (`rmdir`) and copy the file. See [docker/minio/README.md](../docker/minio/README.md). |
| 2 | `AIRFLOW__CORE__FERNET_KEY`, `AIRFLOW__WEBSERVER__SECRET_KEY`, `AIRFLOW__API_AUTH__JWT_SECRET` non-empty in `.env` | Compose `${…:?}` on Airflow services. With `NEXUS_SECRETS_BACKEND=vault`, `setup.sh` does **not** auto-fill these (Vault owns live secrets later). Generate once per host — do not copy WSL values onto EC2. |
| 3 | `SIGNOZ_TOKENIZER_JWT_SECRET` non-empty in `.env` | Same parse-time rule for the included [docker/signoz/compose.yml](../docker/signoz/compose.yml). Leave `signoz` out of `COMPOSE_PROFILES` if you do not want the UI. |

Generate blanks on the host (unique per machine):

```bash
# Airflow crypto (required even without the airflow profile)
python3 - <<'PY'
from pathlib import Path
import base64, os, secrets, re
env = Path(".env")
text = env.read_text()
def set_var(text, key, value):
    if re.search(rf"^{re.escape(key)}=", text, re.M):
        return re.sub(rf"^{re.escape(key)}=.*$", f"{key}={value}", text, count=1, flags=re.M)
    return text.rstrip() + f"\n{key}={value}\n"
text = set_var(text, "AIRFLOW__CORE__FERNET_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
text = set_var(text, "AIRFLOW__WEBSERVER__SECRET_KEY", secrets.token_urlsafe(32))
text = set_var(text, "AIRFLOW__API_AUTH__JWT_SECRET", secrets.token_urlsafe(32))
env.write_text(text)
print("Airflow crypto written to .env")
PY

# SigNoz tokenizer (required even without the signoz profile)
jwt="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
if grep -q '^SIGNOZ_TOKENIZER_JWT_SECRET=' .env; then
  sed -i "s|^SIGNOZ_TOKENIZER_JWT_SECRET=.*|SIGNOZ_TOKENIZER_JWT_SECRET=${jwt}|" .env
else
  printf '\nSIGNOZ_TOKENIZER_JWT_SECRET=%s\n' "${jwt}" >> .env
fi
```

**EC2 / private remote host:** keep `NEXUS_ENV=dev`, `NEXUS_EDGE_MODE=local`, set `NEXUS_PUBLISH_BIND=127.0.0.1`, set `NEXUS_REPO_ROOT` to the absolute clone path, use a new Vault on that machine, and open only SSH (port 22) on the security group. Public HTTPS / `prd` is backlog item **10** — [edge-proxy.md](edge-proxy.md), [environments.md](environments.md).

| Component | Purpose | Where it runs |
| --- | --- | --- |
| Python, uv, DLT, dbt | App / ELT | Host |
| MinIO AIStor Free | Shared S3 object store (no profile; license `.nexusflow/minio.license`) | Docker |
| OTel Collector | Observability gateway → `nexus-telemetry-{env}` (always on) | Docker |
| SigNoz | Trace UI reader (`profile: signoz`) | Docker |
| OpenMetadata | Data catalog reader (`profile: openmetadata`) | Docker |
| ClickHouse | Warehouse (`profile: clickhouse`) | Docker |
| Polaris, Spark Thrift, Trino | Lakehouse (`profile: lakehouse`) | Docker |
| CloudBeaver | Web database IDE (`profile: cloudbeaver`) | Docker |
| Airflow | Orchestration (`profile: airflow`) | Docker |
| HashiCorp Vault | Secrets (`profile: vault` when `NEXUS_SECRETS_BACKEND=vault`) | Docker |

A later CI image for production Python is optional and does not change this Cursor/host workflow. See [architecture.md](architecture.md).

---

## One-command bootstrap

From the repository root (after the [Before first `./scripts/setup.sh`](#before-first-scriptssetupsh-wsl--ec2--vps) checklist):

```bash
cp .env.example .env
mkdir -p .nexusflow
cp /path/to/aistor-license .nexusflow/minio.license
# Generate Airflow + SigNoz Compose-interpolation secrets into .env (see above)
chmod +x scripts/setup.sh
./scripts/setup.sh
```

The script copies `.env` if missing, checks Docker, installs **uv** if missing, starts Vault + MinIO IAM + Compose (using `COMPOSE_PROFILES`; default when unset is `clickhouse,lakehouse`), and runs `uv sync` on the host. It does **not** apt-install Docker on WSL (use Docker Desktop WSL integration). On a bare VPS/EC2, install Docker Engine once, then re-run the script. It does **not** create the MinIO license file or (when `NEXUS_SECRETS_BACKEND=vault`) fill blank Airflow / SigNoz keys in `.env`.

Day to day (deps unchanged):

```bash
./scripts/start.sh              # COMPOSE_PROFILES from .env
./scripts/start.sh all          # every stack — see docs/operations.md
./scripts/start.sh down         # stop everything cleanly
```

Full runbook: [operations.md](operations.md).

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
NEXUS_ENV=dev
# NEXUS_RUN_ID=   # set per load; do not reuse one eternal value

# Which optional stacks to start. MinIO + otel-collector always run (not a profile).
# clickhouse | lakehouse | cloudbeaver | airflow — comma-separated for more than one.
# Airflow is on-demand: omit from the default, or: docker compose --profile airflow up -d
COMPOSE_PROFILES=clickhouse,lakehouse,cloudbeaver

CLICKHOUSE_HOST=localhost
CLICKHOUSE_DB=warehouse
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=change-me

CLICKHOUSE_HTTP_PORT=8123
CLICKHOUSE_NATIVE_PORT=9000

MINIO_API_PORT=9002
MINIO_CONSOLE_PORT=9001

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
```

**AIStor Free license:** copy the downloaded file to **`.nexusflow/minio.license`** (gitignored). Never commit it. See [docker/minio/README.md](../docker/minio/README.md).

On the **VPS**, move passwords and tokens into Vault KV (see [vault.md](vault.md)). Keep only configuration in `.env` when `NEXUS_SECRETS_BACKEND=vault`. Keep the license as that same file path on the VPS clone.

---

## Secrets (HashiCorp Vault)

Full standard: [vault.md](vault.md).

| Mode | `NEXUS_SECRETS_BACKEND` | Where secrets live |
| --- | --- | --- |
| Local WSL / Hostinger VPS | `vault` | Vault KV v2 → Agent → `.nexusflow/secrets.env`; AIStor license → `.nexusflow/minio.license` (gitignored, not in KV) |

`NEXUS_SECRETS_BACKEND=env` is not supported for MinIO writers after backlog item **4** (IAM passwords are not kept in `.env`).

Prefer `./scripts/start.sh` — it loads secrets, unseals Vault when needed, and starts Compose:

```bash
./scripts/start.sh              # COMPOSE_PROFILES from .env
./scripts/start.sh smoke
./scripts/start.sh dbt debug --project-dir branches/dlt_dbt_clickhouse
```

Or manually (license file must already exist as a **file**, not a directory):

```bash
source scripts/load-secrets.sh
docker compose up -d
```

Prefer `./scripts/start.sh` / `./scripts/setup.sh` — those refuse to start if `.nexusflow/minio.license` is missing. Bare `docker compose up` does **not** check; see [docker/minio/README.md](../docker/minio/README.md).

Never commit `.env`, Vault root token, unseal keys, or Agent credentials.

---

## Docker Compose

One file at the repo root. **Profiles name stacks**, not every container. MinIO AIStor Free has no profile so it always starts (license: `.nexusflow/minio.license`). Isolation between capabilities is buckets on that store, not a second Compose project. Design: [architecture.md](architecture.md).

| Profile | Starts | Maps to |
| --- | --- | --- |
| *(none)* | MinIO AIStor Free, otel-collector | Shared object store + observability gateway |
| `clickhouse` | ClickHouse | `dlt_dbt_clickhouse` |
| `lakehouse` | Polaris, Spark Thrift, Trino | `dlt_dbt_spark_iceberg` |
| `cloudbeaver` | CloudBeaver web database IDE | Database administration and SQL exploration |
| `airflow` | Airflow (on-demand) | Orchestration; remote task logs in MinIO |

`COMPOSE_PROFILES` in `.env` is which **containers** run. `config/branches.yaml` is which **pipelines** may execute. Keep them aligned by hand.

```env
# Warehouse day
COMPOSE_PROFILES=clickhouse

# Lakehouse day
COMPOSE_PROFILES=lakehouse

# Both branches (default in .env.example)
COMPOSE_PROFILES=clickhouse,lakehouse

# Both branches plus the web database IDE
COMPOSE_PROFILES=clickhouse,lakehouse,cloudbeaver

# Orchestration day (Airflow UI + scheduler; add to any of the above)
COMPOSE_PROFILES=clickhouse,lakehouse,airflow
```

From the repo root, **start with `./scripts/start.sh`** (checks `.nexusflow/minio.license`). Use Compose directly only for inspect / one-off profiles after the license file already exists:

```bash
./scripts/start.sh              # daily start — license guard + profiles from .env

docker compose ps
docker compose logs
docker compose logs clickhouse
docker compose config
docker compose --profile lakehouse up -d    # one-off; does not need .env change
docker compose --profile cloudbeaver up -d  # one-off; does not need .env change
docker compose --profile airflow up -d      # one-off profile; Airflow secrets must already be in .env
docker compose down          # keeps named volumes
# docker compose down -v     # deletes ClickHouse/MinIO data — avoid
```

Do **not** pair `./scripts/start.sh` with a second `docker compose up -d` in the same step. Bare `docker compose up -d` does not check the license.

Switching stacks: change `COMPOSE_PROFILES` and `docker compose up -d`. Do **not** use `down -v` to switch — that wipes MinIO buckets. `down` without `-v` stops containers and keeps `minio_data` / `clickhouse_data`.

If `.env` has no `COMPOSE_PROFILES`, a bare `docker compose up -d` starts **MinIO AIStor Free only**. `./scripts/setup.sh` defaults to `clickhouse` when the variable is unset. Bare Compose still requires `.nexusflow/minio.license` as a file; a missing path can become a directory — [docker/minio/README.md](../docker/minio/README.md).

There is no application `docker compose build` for Python. Images are pulled. The Airflow image includes the amazon provider used for MinIO remote task logging.

### Ports (from the host)

| Service | URL / port |
| --- | --- |
| ClickHouse HTTP | `localhost:8123` |
| ClickHouse native | `localhost:9000` |
| MinIO API | `localhost:9002` |
| MinIO console | `http://localhost:9001` |
| Polaris REST | `http://localhost:8181` |
| Spark Thrift (dbt-spark) | `localhost:10000` |
| Spark UI | `http://localhost:4040` |
| Trino UI | `http://localhost:8080` |
| CloudBeaver | `http://localhost:8978` |
| Airflow UI | `http://127.0.0.1:8081` |

From **another container**, use Compose DNS: `clickhouse:8123`, `minio:9000`, `polaris:8181`, `spark-thrift:10000`, `trino:8080` (MinIO listens on 9000 inside the network; the host maps API to 9002). CloudBeaver connects to ClickHouse at `clickhouse:8123` and Trino at `trino:8080`; do not use `localhost` for those connections inside CloudBeaver.

### Verify

```bash
curl http://localhost:8123/ping
```

Expected: `Ok.`

Open the MinIO console with credentials from `.env`.

**Lakehouse stack** (when `lakehouse` profile is active):

```bash
curl --fail http://localhost:8182/q/health          # Polaris management health
curl --fail http://localhost:8080/v1/info         # Trino
bash -c 'cat < /dev/null > /dev/tcp/localhost/10000' && echo "Spark Thrift OK"
```

Trino CLI (inside container): `docker exec -it trino trino --catalog nexus_dev`

CloudBeaver opens at `http://localhost:8978`. Its users, settings, and saved connections persist in the named `cloudbeaver_workspace` volume. Do not use `docker compose down -v` unless you intend to delete named volumes.

**Airflow** (when `airflow` profile is active):

```bash
curl --fail http://127.0.0.1:8081/api/v2/monitor/health
```

UI login uses `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` (example default `admin` / `change-me`, local WSL only — change on a VPS). `AIRFLOW__CORE__FERNET_KEY`, `AIRFLOW__WEBSERVER__SECRET_KEY`, and `AIRFLOW__API_AUTH__JWT_SECRET` are required; `./scripts/setup.sh` generates them when blank. **First time on WSL or a VPS:** follow the checklist in [orchestration/airflow/README.md](../orchestration/airflow/README.md) (`.env` host user/path, then `./scripts/start.sh airflow`). Trigger `nexus_airflow_smoke` to verify the scheduler; trigger `route_clickhouse_products` for the first ELT job. Airflow is **3.3.2** (api-server + dag-processor; not 2.x).

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

Warehouse Route `products` dlt is live (env = dbt `--target`; default `dev`). Warehouse vs lakehouse: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md). Route endpoints: [route-ingestion.md](route-ingestion.md). Prefer `unset NEXUS_RUN_ID` so the script mints a fresh id (leftover shell exports override minting).

```bash
set -a && source .env && set +a
export NEXUS_ENV=dev
unset NEXUS_RUN_ID
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4317}"
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py
# Optional explicit id (Airflow / replay / dlt→dbt chain):
# uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py --run-id local-20260905T120000Z
# After dbt models exist, pass the same run_id as var('run_id'):
# export NEXUS_RUN_ID=…   # from the products.py print line, or --run-id
# uv run dbt run --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
#   --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
# uv run dbt test --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV"
```

Lakehouse (Milestone 2, Spark Thrift required): `--project-dir branches/dlt_dbt_spark_iceberg` and `branches/dlt_dbt_spark_iceberg/dlt/route/products.py`.

dbt uses `~/.dbt/profiles.yml` unless you pass `--profiles-dir`. Profile names match Compose stacks: **`nexus_clickhouse`**, **`nexus_lakehouse`**. Passwords and hosts come from **environment variables only** (never hardcode secrets in `profiles.yml`).

dbt does **not** load the repo `.env`. Source config and secrets before every dbt command:

```bash
# VPS (after Vault): source scripts/load-secrets.sh
set -a && source .env && set +a
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse
uv run dbt debug --project-dir branches/dlt_dbt_spark_iceberg
```

On the VPS with Vault, use `scripts/load-secrets.sh` instead of sourcing `.env` alone. See [vault.md](vault.md).

Optional project copy: `profiles.example.yml` → `profiles.yml` in the branch folder (gitignored). Do not commit `profiles.yml`.

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
