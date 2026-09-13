# terraform

Repeatable **dev** and **prd** environments. Phase 2. Not implemented yet.

Modules must emit the names already locked in [docs/environments.md](../../docs/environments.md) (`bronze_{env}`, `{purpose}-{env}` buckets, ClickHouse users in [docs/rbac.md](../../docs/rbac.md)). They do not invent a second naming scheme or replace Compose/host `uv`.
