# common

Shared Python helpers used across branches (not tied to one execution branch).

- `common/observability/` — observability data lake SDK (MinIO `nexus-telemetry-{env}`). See [docs/observability.md](../docs/observability.md).
- `common/branches.py` — `config/branches.yaml` enabled check.
- `common/runtime_env.py` — `load_runtime_env(repo_root)` for host `.env` / Vault Agent; no-op when `NEXUS_ELT_JOB=1`.

Import from repo root: `uv run python -c "from common.observability import ..."` or use `./scripts/start.sh` (sets `PYTHONPATH` to repo root).
