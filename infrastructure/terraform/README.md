# terraform

Repeatable **dev** (local first) and later **prd** environments. Not implemented yet.

**Delivery order:** [docs/backlog.md](../../docs/backlog.md) — **local** Terraform = item **5**; Actions + VPS edge/`prd` = item **10**.

**License:** HashiCorp Terraform only (BSL 1.1). No OpenTofu. No Ansible. CLI binary is `terraform`.

**CI/CD pairing:** GitHub Actions (item **10**) runs `terraform plan` / `apply` and VPS deploy. Local item **5** applies against Compose endpoints. Terraform does **not** replace Actions, Compose, or host `uv`. Full intent: [docs/ci-cd.md](../../docs/ci-cd.md).

Modules must emit the names already locked in [docs/environments.md](../../docs/environments.md) (`bronze_{env}`, `{purpose}-{env}` buckets, ClickHouse users in [docs/rbac.md](../../docs/rbac.md)). They do not invent a second naming scheme.

## Dual ownership (resolve when implementing backlog item 5)

Buckets and ClickHouse users are created today by `minio-init` and `clickhouse-rbac-bootstrap.sh`. When item **5** starts, plan the cutover so Terraform and those scripts do not both Create the same objects. Options and note: [docs/backlog.md](../../docs/backlog.md) § item 5. Do not implement the cutover until that backlog item is in progress.

## Edge proxy / public hostname (required when exposing UIs)

Local WSL and VPS are **different modes**. Do not reuse local hosts-file + HTTP settings on a public VM.

VPS Terraform (backlog item **10**, invoked from GitHub Actions) **must** implement the checklist in [docs/edge-proxy.md](../../docs/edge-proxy.md#deployment-contract-terraform--github-actions--backlog-item-10):

- `NEXUS_EDGE_MODE=vps`
- DNS for `*.${NEXUS_PUBLIC_HOST}` (not `proxy-hosts.sh`)
- HTTPS via `NEXUS_EDGE_MODE=vps` (loads `Caddyfile.vps`; rejects `http://` scheme; requires ACME email)
- `NEXUS_PUBLISH_BIND=127.0.0.1` for backends (Compose **default**; **start.sh** and Caddy entrypoint reject `0.0.0.0` when mode=vps); Caddy 80/443 public; host firewall 22/80/443
- Compose profile `proxy` on the VPS
- Vault secrets on the machine; auth gate before public `docs.` / `elementary.` / home

Until that contract is implemented, keep the edge **local-only**.
