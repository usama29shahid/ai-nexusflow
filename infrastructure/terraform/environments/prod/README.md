# terraform/environments/prod

`prd` environment (folder name `prod`; object suffix is **`prd`**). Phase 2. Not implemented yet.

Creates `NEXUS_ENV=prd` names (`bronze_prd`, `nexus-*-prd`, …). Same dlt/dbt/DAG codebase as `dev`; env is target/config, not a forked repo.
