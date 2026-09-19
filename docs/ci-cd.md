# CI/CD and production-ready local (locked intent)

**Goal:** make the repo as **production-shaped on WSL** as practical, so **day-one VPS cutover is automated** through **GitHub Actions + Terraform**. Prefer **GitHub Actions for all CI/CD** (lint, test, build images, plan/apply, deploy). Do not invent a second deploy tool (Jenkins, ad-hoc SSH runbooks as the primary path, manual “copy `.env` to the server”).

Phase 1 builds the runnable platform. Phase 2 **wires** Actions + Terraform. Do not implement speculative workflows before Phase 1 Milestone 1 is solid ([roadmap.md](roadmap.md)).

## Who owns what

| Concern | Owner | Notes |
| --- | --- | --- |
| Lint / unit tests / image builds | **GitHub Actions** | Same commands developers run (`uv run`, `docker build`) |
| Environment identity (`dev` / `prd`), DNS, firewall baseline, rendered server env | **Terraform** | Creates names in [environments.md](environments.md); sets `NEXUS_EDGE_MODE=vps`, `NEXUS_PUBLIC_HOST`, etc. |
| Bring stacks up / ELT | **`./scripts/start.sh`** on the host (or Actions invoking it over SSH) | Actions is **not** a second ingest/transform runner |
| Secrets on VPS | **Vault + Agent** | [vault.md](vault.md); Actions may trigger deploy, not bake secrets into git |
| Local vs public edge | **`NEXUS_EDGE_MODE`** | `local` → `Caddyfile.local` (HTTP); `vps` → `Caddyfile.vps` (HTTPS). Entrypoint selects file — no SSH edit ([edge-proxy.md](edge-proxy.md)) |

```text
Developer push → GitHub Actions
  → lint + tests (+ optional image build)
  → terraform plan/apply (env / DNS / server config)     [Phase 2]
  → deploy: git pull + ./scripts/start.sh on VPS         [Phase 2]
  → Airflow / dlt / dbt still run on the VPS host path     (unchanged)
```

## Production-ready on local (what “done” means before day-one deploy)

Build these **now** (Phase 1) so Actions/Terraform only **connect** them later:

1. **One codebase, one Compose file, one `start.sh`** — no “prod fork” of pipelines.
2. **Names already final** — `bronze_{env}`, buckets `{purpose}-{env}`, RBAC users ([environments.md](environments.md), [rbac.md](rbac.md)).
3. **Secrets contract** — apps read env vars; local may use `NEXUS_SECRETS_BACKEND=env`; VPS uses `vault` with the **same var names**.
4. **Edge routes exist locally** — Caddy profile `proxy` + subdomains; VPS flips mode (`NEXUS_EDGE_MODE=vps`, ACME email, empty scheme, `NEXUS_PUBLISH_BIND=127.0.0.1`), not a new proxy product ([edge-proxy.md](edge-proxy.md)).
5. **ELT path matches VPS** — `nexus-elt` job image + Airflow DAG pattern already used locally.
6. **Tests runnable headlessly** — `uv run python tests/...` suitable for Actions.
7. **No WSL-only secrets in git** — `.env` / `.nexusflow` stay uncommitted; `.env.example` documents both local and VPS examples.

Local still differs where it must: hosts file + HTTP, optional weak lab passwords, not every profile always on. That is **mode**, not a second architecture.

## Day-one deploy (Phase 2 — automated)

When Phase 2 lands, a typical first production cutover should be **Actions-driven**, not a long manual checklist:

1. Terraform applies `dev` (or `prd`) env resources + DNS + server env including `NEXUS_EDGE_MODE=vps`.
2. Actions builds/pushes required images if needed (`nexus-elt`, Airflow image).
3. Actions deploys to the VPS: clone/pull, Vault ensure, `./scripts/start.sh` with the VPS profile set (including `proxy`).
4. Smoke: health URLs on `https://…` (or Actions curl against public hostnames).

Manual steps that remain acceptable (document in the workflow README when written): one-time VPS bootstrap (Docker, uv, Vault init/unseal policy), DNS registrar login if not fully API-driven, first auth-gate secrets (Supabase/Google). Everything else should be Actions + Terraform.

## Explicit non-goals

- GitHub Actions as a place that runs dlt/dbt ingest (no second ELT runner).
- Copying WSL `.env` onto the VPS via Actions.
- Using `proxy-hosts.sh` as production DNS.
- A second Compose “prod stack” or `prd` git branch.

## Pointers

- Edge / local vs VPS checklist: [edge-proxy.md](edge-proxy.md)
- Env names + additive Phase 2 rules: [environments.md](environments.md)
- Terraform stub + edge requirements: [infrastructure/terraform/README.md](../infrastructure/terraform/README.md)
- Vault: [vault.md](vault.md)
- Roadmap Phase 2: [roadmap.md](roadmap.md)
