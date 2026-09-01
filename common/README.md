# common

Shared Python helpers used across branches (not tied to one execution branch).

- `common/observability/` — observability data lake SDK (MinIO `nexus-telemetry-{env}`). See [docs/observability.md](../docs/observability.md).

Import from repo root: `uv run python -c "from common.observability import ..."` or use `./scripts/start.sh` (sets `PYTHONPATH` to repo root).
