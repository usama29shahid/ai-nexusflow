# terraform

Repeatable **dev** and **prd** environments. Phase 2. Not implemented yet.

**CI/CD pairing:** GitHub Actions runs `terraform plan` / `apply` and VPS deploy. Terraform does **not** replace Actions, and Actions does **not** invent a second naming scheme. Full intent: [docs/ci-cd.md](../../docs/ci-cd.md).

Modules must emit the names already locked in [docs/environments.md](../../docs/environments.md) (`bronze_{env}`, `{purpose}-{env}` buckets, ClickHouse users in [docs/rbac.md](../../docs/rbac.md)). They do not invent a second naming scheme or replace Compose/host `uv`.

## Edge proxy / public hostname (required when exposing UIs)

Local WSL and VPS are **different modes**. Do not reuse local hosts-file + HTTP settings on a public VM.

Terraform (invoked from GitHub Actions) **must** implement the checklist in [docs/edge-proxy.md](../../docs/edge-proxy.md#deployment-contract-terraform--github-actions--phase-2):

- `NEXUS_EDGE_MODE=vps`
- DNS for `*.${NEXUS_PUBLIC_HOST}` (not `proxy-hosts.sh`)
- HTTPS via `NEXUS_EDGE_MODE=vps` (loads `Caddyfile.vps`; rejects `http://` scheme; requires ACME email)
- `NEXUS_PUBLISH_BIND=127.0.0.1` for backends (Compose **default**; **start.sh** and Caddy entrypoint reject `0.0.0.0` when mode=vps); Caddy 80/443 public; host firewall 22/80/443

- Compose profile `proxy` on the VPS
- Vault secrets on the machine; auth gate before public `docs.` / `elementary.` / home

Until that contract is implemented, keep the edge **local-only**.
