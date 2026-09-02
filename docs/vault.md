# HashiCorp Vault (secrets management)

Single source of truth for **how AI-NexusFlow stores and injects secrets** on the Hostinger VPS (and optionally WSL once Vault is running locally).

Related:

- [Development setup](setup.md) — Compose, host Python, bootstrap
- [dlt extraction](dlt-extraction.md) — dlt reads secrets from the environment
- [Environments](environments.md) — `NEXUS_ENV` and naming
- [Architecture](architecture.md) — infra on host vs Docker

Official HashiCorp references:

- [Vault documentation](https://developer.hashicorp.com/vault/docs)
- [KV secrets engine v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
- [Vault Agent](https://developer.hashicorp.com/vault/docs/agent)
- [AppRole auth](https://developer.hashicorp.com/vault/docs/auth/approle)

---

## Purpose

Replace **plaintext secrets in `.env`** on shared hosts (Hostinger VPS) with **HashiCorp Vault** as the secret store. Application code (dlt, dbt, Docker Compose) **does not call Vault directly** — **Vault Agent** renders secrets into a host env file that existing scripts already `source`.

```text
HashiCorp Vault (Docker)
  → Vault Agent (Docker)
  → .nexusflow/secrets.env (repo-local, gitignored)
  → source .env + secrets.env
  → docker compose | uv run dlt | dbt
```

**dlt and dbt never import a Vault SDK.** They read the same environment variable names as today (`CLICKHOUSE_PASSWORD`, `MINIO_ROOT_PASSWORD`, …).

---

## Why HashiCorp Vault

| Reason | Detail |
| --- | --- |
| Industry standard | Widely used in enterprise and platform engineering |
| Fits this stack | **Vault Agent** injects env vars — matches Compose + host Python/dbt with no pipeline code changes |
| AWS experience | KV v2 paths + AppRole map to AWS Secrets Manager secret names + IAM-style access |
| Project alignment | [dlt-extraction.md](dlt-extraction.md) and [config/prod.yaml](../config/prod.yaml) already expect a secret manager |

**Not in scope for Phase 1:** Vault Enterprise (DR replication, performance replication), HCP Vault Dedicated (optional later — same API).

---

## License and edition

HashiCorp Vault is **free to self-host** and **source-available**. Since 2023 it is licensed under **Business Source License (BSL) 1.1** — not an OSI-approved open-source license.

| Topic | For this project |
| --- | --- |
| Cost on VPS | **$0** — self-hosted Community edition |
| License | **BSL 1.1** — allowed for internal / self-hosted use; do not offer a competing managed Vault service |
| Phase 1 features | KV v2, AppRole, integrated Raft storage, Vault Agent, ACL policies |
| Enterprise-only | DR replication, performance replication, advanced governance (not required now) |

Document and describe Vault as **“HashiCorp Vault (BSL, free self-hosted)”** — accurate for a portfolio project.

---

## Secret backend modes

Controlled by `NEXUS_SECRETS_BACKEND` in `.env`:

| Value | When | Behavior |
| --- | --- | --- |
| `env` | WSL local bootstrap, or when Vault is not enabled | Secrets live in `.env` only |
| `vault` | Hostinger VPS (target default) | Secrets **must** come from Agent-rendered `.nexusflow/secrets.env`; `.env` holds config only |

When `NEXUS_SECRETS_BACKEND=vault`, `./scripts/setup.sh` and manual runs **must** source secrets via `scripts/load-secrets.sh`. Missing Agent output **fails fast** with a clear message.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ Host (WSL / Hostinger VPS)                                  │
│  .env                    — NEXUS_ENV, ports, COMPOSE_…      │
│  .nexusflow/secrets.env   — Agent-rendered (gitignored)     │
│  scripts/load-secrets.sh — source .env + secrets.env        │
│  uv run dlt / dbt        — read os.environ                  │
└───────────────────────────┬─────────────────────────────────┘
                            │ VAULT_ADDR (localhost)
┌───────────────────────────▼─────────────────────────────────┐
│ Docker: hashicorp/vault (Raft storage, single-node)         │
│  KV v2: secret/nexusflow/{env}/…                            │
└─────────────────────────────────────────────────────────────┘
```

Vault API listens on **`127.0.0.1:8200`** only — not exposed to the public internet on the VPS.

---

## What stays in `.env` vs Vault

### `.env` (configuration — safe to treat as non-secret on VPS after cutover)

| Variable | Purpose |
| --- | --- |
| `NEXUS_ENV` | `dev` until Terraform (`prd` naming contract later) |
| `NEXUS_SECRETS_BACKEND` | `env` or `vault` |
| `VAULT_ADDR` | e.g. `http://127.0.0.1:8200` |
| `COMPOSE_PROFILES` | Which Docker stacks start |
| Hosts and ports | `CLICKHOUSE_HOST`, `MINIO_API_PORT`, … |
| `POLARIS_CLIENT_ID` | OAuth client id (secret is `POLARIS_CLIENT_SECRET` in Vault) |

### Vault KV v2 (secrets — never commit)

Base path: **`secret/nexusflow/{env}/`** where `{env}` matches `NEXUS_ENV` (e.g. `dev`).

| Vault path (under `secret/nexusflow/dev/`) | Keys in Vault | Rendered env var(s) | Used by |
| --- | --- | --- | --- |
| `clickhouse` | `password` | `CLICKHOUSE_PASSWORD` | Compose, dbt |
| `minio` | `root_user`, `root_password` | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | Compose, dlt archive |
| `polaris` | `client_secret` | `POLARIS_CLIENT_SECRET` | lakehouse profile |
| `airflow` | `fernet_key`, `web_secret`, `admin_password` | `AIRFLOW__CORE__FERNET_KEY`, `AIRFLOW__WEBSERVER__SECRET_KEY`, `AIRFLOW_ADMIN_PASSWORD` | airflow profile |
| *(future)* `route` | JWT / demo-user secrets when authenticated entities are implemented | TBD | dlt Route user entities — **not required for catalog-only** |

Catalog-first Route ingestion needs no Vault path. Do not seed unused source secrets.

Example write (after bootstrap — operator shell only):

```bash
vault kv put secret/nexusflow/dev/clickhouse password='strong-random-password'
vault kv put secret/nexusflow/dev/minio root_user='minioadmin' root_password='strong-random-password'
```

---

## AWS Secrets Manager mapping

If you have used AWS Secrets Manager, the mapping is:

| AWS Secrets Manager | HashiCorp Vault (this project) |
| --- | --- |
| Secret name / ARN | KV v2 path, e.g. `secret/nexusflow/dev/clickhouse` |
| Secret JSON fields | Vault key-value pairs under that path |
| IAM role → `GetSecretValue` | **AppRole** → Vault Agent reads KV |
| ECS/Lambda env injection | **Vault Agent template** → `.nexusflow/secrets.env` |
| App reads env vars | Same — dlt/dbt read `os.environ` |

**Platform injects secrets; applications never fetch them directly.**

---

## Vault Agent contract

Implemented under `docker/vault/` using the official [Vault Agent](https://developer.hashicorp.com/vault/docs/agent) pattern:

1. **Auth:** AppRole (`role_id` on host with restricted permissions; `secret_id` short-lived or from secure bootstrap)
2. **Template:** `docker/vault/templates/secrets.env.tpl` → `.nexusflow/secrets.env`
3. **AppRole:** `.nexusflow/approle/` + generated `.nexusflow/agent-autoauth.hcl` (gitignored)
4. **Permissions:** rendered `secrets.env` mode **`0640`** (owner + group read); AppRole credentials **`0600`** under `.nexusflow/approle/` (`700` dir — admin/bootstrap only)

Example template shape:

```text
CLICKHOUSE_PASSWORD={{ with secret "secret/data/nexusflow/dev/clickhouse" }}{{ .Data.data.password }}{{ end }}
MINIO_ROOT_PASSWORD={{ with secret "secret/data/nexusflow/dev/minio" }}{{ .Data.data.root_password }}{{ end }}
```

Note: KV v2 read paths use `secret/data/…`; write paths use `secret/nexusflow/…`.

---

## Host command pattern

dbt does **not** load `.env` automatically. Prefer the single entrypoint:

```bash
./scripts/start.sh              # secrets + compose up
./scripts/start.sh smoke
./scripts/start.sh dbt run --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
  --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
./scripts/start.sh shell        # interactive shell with secrets
```

Or manually:

```bash
source scripts/load-secrets.sh
```

When `NEXUS_SECRETS_BACKEND=env`, `./scripts/start.sh` sources `.env` only.

---

## Bootstrap checklist (VPS)

One-time (store **recovery keys** and **root token** offline — password manager or encrypted backup, not in git):

1. Set `NEXUS_SECRETS_BACKEND=vault` in `.env`
2. Run `./scripts/setup.sh` or `./scripts/start.sh vault` (init, unseal, seed missing KV paths, start Agent)
3. Confirm `.nexusflow/secrets.env` exists, mode `640`, and bootstrap user can read it (`source scripts/load-secrets.sh`). Bootstrap **exits with error** if the file exists but is not readable — run the printed `sudo chown …` once if Agent wrote it as root.
4. Run smoke: `./scripts/start.sh smoke` and dbt `stg_dlt_smoke_smoke`

**Do not** commit root token, unseal keys, AppRole `secret_id`, or `secrets.env`.

---

## Daily operations

### Rotate a secret

1. Write new version: `vault kv put secret/nexusflow/dev/clickhouse password='new-value'`
2. Reload Vault Agent (or restart Agent service)
3. Restart affected containers if they already started with old env: `docker compose up -d --force-recreate clickhouse` (example)
4. Re-run dbt/dlt as needed

### Backup

```bash
vault operator raft snapshot save nexusflow-vault-$(date -u +%Y%m%d).snap
```

Store snapshots **off the VPS** (encrypted object storage or local secure copy).

### After VPS reboot

Vault seals on restart. Commands that need credentials (`smoke`, `dbt`, stack starts) run **`scripts/vault-ensure.sh`** (fast path: unseal if sealed, ensure Agent, source `secrets.env`). Falls back to full **`vault-bootstrap.sh`** on first run or missing secrets. Infra-only commands (`stop-signoz`, etc.) skip Vault. Explicit full bootstrap: `./scripts/start.sh vault`.

To run Vault only:

```bash
./scripts/start.sh vault
```

---

## VPS hardening (Hostinger)

| Control | Rule |
| --- | --- |
| Vault API | Bind **`127.0.0.1:8200`** — not `0.0.0.0` on a public VPS |
| Firewall | Allow SSH and required app ports; **deny inbound 8200** from the internet |
| Root token | Use only for bootstrap; prefer limited policies + AppRole for Agent |
| `.env` on VPS | No real passwords after cutover — config only |
| Source API tokens | Only when a source needs them (Route catalog needs none; JWT later) |
| Default passwords | Replace dev defaults (`clickhouse123`, `minioadmin123`, …) when seeding Vault |

### Admin + dev user (optional)

For a **solo admin** plus a **dev user** without full root:

1. Create a shared group, e.g. `sudo groupadd nexusflow` and add both users: `sudo usermod -aG nexusflow admin` / `dev`.
2. Set `NEXUS_SECRETS_GROUP=nexusflow` in `.env`.
3. Run Vault bootstrap as **admin** (`./scripts/setup.sh` or `./scripts/start.sh vault`). Bootstrap sets:
   - `.nexusflow/secrets.env` → **`640`** (`admin:nexusflow`) — dev can `source scripts/load-secrets.sh` and run smoke/dbt
   - `.nexusflow/approle/`, `vault-init.json`, `agent-autoauth.hcl` → **admin-only** (`700` / `600`) — dev does not get Vault Agent or root credentials
4. If Agent wrote `secrets.env` as root, admin runs once: `sudo chown admin:nexusflow .nexusflow/secrets.env && chmod 640 .nexusflow/secrets.env`

Solo developer (no shared group): omit `NEXUS_SECRETS_GROUP`; bootstrap uses your primary group and **`640`** on `secrets.env` (you remain owner).

---

## AWS secrets (complementary, Phase 2+)

When [Terraform](roadmap.md) lands on AWS:

- **AWS Secrets Manager** is a natural choice for AWS-native resources (RDS, ECS, Lambda)
- **HashiCorp Vault** (self-hosted on VPS or **HCP Vault Dedicated**) remains valid for multi-cloud or matching local behavior
- This project keeps **env injection** in dlt/dbt either way — migrating KV paths to AWS SM is an infra change, not a pipeline rewrite

---

## What applications must not do

- Do **not** add `hvac` or other Vault SDK calls inside dlt or dbt
- Do **not** commit `.env`, `secrets.env`, root token, unseal keys, or AppRole credentials
- Do **not** hardcode secrets in `profiles.yml`, Python, or dbt models
- Do **not** use `vault server -dev` on the VPS (in-memory, insecure)
- Do **not** expose Vault UI/API on the public internet

Fail clearly in dlt when a required secret env var is missing (for example a future Route JWT env var for authenticated entities).

---

## Implementation status

| Status | Item |
| --- | --- |
| Done | This document |
| Done | `docker/vault/` config, Agent template, policy |
| Done | Vault + vault-agent services in `docker-compose.yml` (`profile: vault`) |
| Done | `scripts/vault-ensure.sh`, `scripts/vault-bootstrap.sh`, `scripts/load-secrets.sh` |
| Done | Verified: `dlt_clickhouse_smoke` with Vault-injected secrets |
| Planned | Route catalog ingestion (no secrets); JWT secrets only when authenticated entities are added |

Read this document before changing secrets layout, bootstrap scripts, or Compose Vault services.
