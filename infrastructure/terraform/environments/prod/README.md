# terraform/environments/prod

`prd` environment (folder name `prod`; object suffix is **`prd`**). Not implemented yet — [docs/backlog.md](../../../../docs/backlog.md) item **10**.

Creates `NEXUS_ENV=prd` names (`bronze_prd`, `nexus-*-prd`, …). Same dlt/dbt/DAG codebase as `dev`; env is target/config, not a forked repo.
