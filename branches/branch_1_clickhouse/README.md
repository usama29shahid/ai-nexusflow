# Branch 1 — ClickHouse warehouse ELT

```text
Source → DLT → ClickHouse (RAW) → dbt → ClickHouse (TRANS)
```

dbt project: `dbt/` (name `nexus_dbt`). Copy `dbt/profiles.example.yml` → `dbt/profiles.yml` before the first run. Pipeline code is not implemented yet.
