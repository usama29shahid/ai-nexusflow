# LLM/RAG Pipeline Generation Vision

> **⚠️ This is not the final design for the UI.**
>
> The UI examples in this document are illustrative expectations only. Final
> pages, layouts, embedding strategy, authentication, and interactions will be
> decided after the data pipelines and Airflow execution are stable.

## Purpose and status

This document is a future reference for the Phase 2 LLM/RAG capability. It
describes the intended logic for turning a natural-language ELT requirement
into reviewed, validated, and executable artifacts, plus the information a
future Streamlit portfolio/control dashboard may present.

This is a vision document, not an implementation specification. The existing
architecture, branch, extraction, modeling, environment, observability, and
roadmap documents remain authoritative:

- [Architecture](architecture.md)
- [Roadmap](roadmap.md)
- [dlt extraction](dlt-extraction.md)
- [ClickHouse ELT](dlt-dbt-clickhouse.md)
- [dbt modeling](dbt-modeling.md)
- [Observability](observability.md)
- [Environments](environments.md)

The capability depends on the earlier phases being runnable. Phase 1 delivers the data branches, Airflow orchestration, and the observability data lake. This vision must not delay the first working ELT vertical slice.

## Illustrative user requirement

The following is an example of the kind of request the future system may
accept:

```text
Deploy the PokeAPI REST endpoint into ClickHouse. Keep the raw response in the
MinIO archive and ClickHouse Bronze, create staging and Gold models, and make
the Gold entity an SCD Type 2 dimension using pokemon_id as its natural key.
```

This example does not establish a default modeling policy. Bronze, staging,
intermediate, Gold, marts, facts, events, and SCD2 are selected according to
the requirement and the retrieved project standards. In particular, SCD2 is
not required for every source or Gold model.

## Conceptual lifecycle

```text
Natural-language requirement
  → Planner
  → RAG standards retrieval
  → Structured ELT specification
  → Deterministic validation
  → Artifact preview
  → Human approval
  → Artifact deployment
  → Airflow DAG execution
  → dlt + dbt results
  → documentation, lineage, and health status
```

### 1. Planner

The planner interprets the requirement and identifies:

- source type, source name, endpoint, authentication, pagination, and
  incremental behavior;
- destination and required execution branch;
- requested layers, model grains, keys, tracked attributes, and history
  requirements;
- schedule, retry, and operational expectations;
- required tests and consumer outputs.

The planner reasons over the request. It does not invent unsupported
capabilities or organization conventions.

### 2. RAG standards retrieval

RAG supplies the relevant project or organization rules, including:

- enabled branch and runtime rules;
- dlt extraction, retries, pagination, archival, and Bronze conventions;
- ClickHouse or Iceberg physical naming;
- dbt folder, source, model, grain, and test conventions;
- SCD, incremental, deduplication, and replay patterns;
- Airflow DAG grain, selectors, retries, and run-ID rules;
- environment and observability requirements.

The LLM provides reasoning; RAG provides the standards and constraints.

### 3. Structured ELT specification

The planner produces a reviewable specification before code generation. The
future shape may include:

```yaml
pipeline:
  name: pokeapi_to_clickhouse
  source: pokeapi
  endpoints: [pokemon]
  branch: dlt_dbt_clickhouse
  destination: clickhouse

ingestion:
  archive: minio
  write_disposition: append

models:
  staging: [stg_pokemon]
  gold:
    - name: dim_pokemon
      grain: one row per pokemon version
      scd_type: 2
      natural_key: pokemon_id

orchestration:
  dag_grain: source
  schedule: daily
```

This is illustrative only. The final schema and validation contract will be
designed when the generator is implemented.

### 4. Deterministic validation

Validation must happen independently of the LLM and must reject:

- disabled or unavailable branches;
- missing or unreachable required runtimes;
- invalid schedules or unsupported execution patterns;
- invalid physical names or environment handling;
- unsupported source, destination, or modeling capabilities;
- missing business keys or ambiguous grain;
- missing required tests;
- conflicts with an existing pipeline or artifact;
- violations of the documented dlt/dbt/Airflow ownership boundaries.

Validation failures should be actionable and returned before artifacts are
written or deployed.

### 5. Artifact preview and approval

The generator may produce:

- branch-owned dlt extraction code;
- dbt source definitions, models, tests, and documentation metadata;
- an Airflow DAG or source-DAG update;
- selectors, configuration, and a generated pipeline specification.

The expected workflow is preview first, then explicit human approval before
writing or deploying generated artifacts. Automatic deployment is not a
default assumption.

Generated artifacts must follow the existing repository boundaries. For
example, ClickHouse capability dlt code belongs under
`branches/dlt_dbt_clickhouse/dlt/{source}/`; it must not create an unrelated
top-level pipeline implementation.

## Execution expectations

After approval and deployment, the expected ClickHouse capability flow is:

```text
Airflow source DAG
  ├── endpoint-level dlt task(s)
  │     ├── MinIO immutable raw archive
  │     └── ClickHouse Bronze append
  └── dbt selector task(s)
        ├── staging / intermediate / Gold as required
        ├── dbt tests
        └── dbt documentation artifacts
```

The repository standard is one DAG per source with endpoint-level dlt tasks,
not one DAG per REST URL. Domain-only dbt work may use a dbt selector without
creating another extraction pipeline.

### Ownership and run identity

- dlt owns REST authentication, pagination, retries, rate limits, incremental
  state, raw archival, and Bronze loading.
- dbt owns staging, intermediate, Gold, marts, tests, and model documentation.
- Airflow owns scheduling, task dependencies, retries, and operational logs.
- MinIO stores the immutable raw archive and, later, Airflow remote logs in
  their separate buckets. The raw archive is not the ClickHouse analytical
  Gold layer.
- The same run identity is explicitly passed to dlt and dbt. A task-local
  environment variable must not be assumed to persist into another Airflow
  task.

The future Airflow runtime topology must preserve the current development
expectation that dlt and dbt run from the host while Airflow infrastructure
runs in Docker. The exact host execution bridge is intentionally left for a
later Airflow design decision; bind-mounting a developer `.venv` into a
container is not the contract.

### SCD2 expectation

When a requirement explicitly requests SCD2, the generated design must define:

- the natural/business key;
- tracked attributes;
- version start and end semantics;
- current-row semantics;
- replay and late-arriving behavior;
- tests for key, grain, and current-state correctness.

ClickHouse SCD2 must follow a verified ClickHouse-compatible insert-only
strategy. A generic dbt incremental template must not be assumed to update
previous rows or correctly expire current records.

## Illustrative Streamlit expectations

Streamlit is a future lightweight portfolio and control dashboard. It is not a
replacement for Airflow, dbt Docs, CloudBeaver, or MinIO, and it must not become
the execution engine or operational source of truth.

> **⚠️ This is not the final design for the UI.**
>
> The following sections describe what a future demo may show, not a committed
> page structure or interaction design.

### Pipeline catalog

A future dashboard may show:

- pipeline name, source, endpoint, branch, and destination;
- schedule and generated-artifact status;
- latest run and current health;
- links to Airflow, dbt Docs, CloudBeaver, MinIO, and project documentation.

### Airflow DAG and execution

Streamlit may display or link to:

- available DAGs and paused/unpaused state;
- latest DAG run and task-level progress;
- dlt, dbt, test, and documentation task states;
- a future authenticated “Trigger DAG” action through the Airflow API;
- the complete Airflow DAG graph and task logs.

Airflow remains the authority for scheduling, retries, task execution, and
operational logs. Streamlit should summarize Airflow state rather than
reconstructing Airflow’s scheduler or task engine.

### dbt lineage and documentation

Streamlit may provide:

- a link to generated dbt Docs;
- documentation-artifact availability;
- model and test result summaries from dbt artifacts;
- optional dbt Docs embedding if deployment headers and authentication permit
  it.

dbt Docs remains the authority for dbt model/source lineage, descriptions,
columns, tests, and dependencies. A reliable link is preferred over making an
iframe a required dependency.

### MinIO archive and storage

Streamlit may summarize or link to:

- raw archive bucket and source prefix;
- latest archive run;
- object count or archive status;
- environment and archive location;
- MinIO Console;
- the distinction between raw data archives and Airflow operational logs.

MinIO remains the object-storage authority. Streamlit should not duplicate its
object-browser functionality.

### Pipeline health and progress

A future dashboard may summarize:

- Airflow DAG and task states;
- dlt load success and row counts;
- MinIO archive status;
- Bronze, Silver, and Gold row counts;
- dbt model results from `run_results.json`;
- dbt test results;
- latest shared run ID;
- execution duration;
- dbt Docs refresh status.

No custom logging database should be introduced for this purpose. Streamlit
should read Airflow state, dbt artifacts, dlt metadata, ClickHouse/Trino
metadata, and MinIO metadata where appropriate.

### Data explorer

A future demo may provide:

- a link to CloudBeaver for full SQL exploration;
- curated read-only Streamlit queries for Gold, SCD2, Bronze, or load-summary
  examples;
- a future Trino link when the Iceberg branch is implemented.

CloudBeaver remains the primary database exploration tool. Streamlit should
not reimplement CloudBeaver or expose an unrestricted public SQL editor.

### Project explanation

The dashboard may link to:

- architecture documentation;
- dbt modeling standards;
- extraction standards;
- observability rules;
- roadmap;
- generated pipeline specification;
- generated artifact preview;
- dbt Docs, Airflow, CloudBeaver, and MinIO.

## Phase boundaries

This vision belongs to **Phase 2** (LLM) and must not pull future work into the current vertical slice.

### Before this capability

- Verify `dlt_dbt_clickhouse` end to end with observability lake writes.
- Verify the lakehouse capability and Branch 3 according to the roadmap.
- Airflow orchestration over enabled capabilities (Phase 1).
- Establish stable dlt, dbt, run-ID, artifact, and observability contracts.

### Deferred by this document

This document does not implement:

- generated dlt, dbt, or Airflow code;
- RAG indexing, embeddings, vector stores, or LLM integrations;
- Streamlit pages or final UI layouts;
- Airflow services or DAGs;
- final public APIs or specification schemas;
- automatic deployment or self-healing behavior;
- a custom operational logging platform.

## Future brainstorming questions

The following decisions remain intentionally open:

- What is the final versioned ELT specification schema?
- How are generated artifacts reviewed, diffed, committed, and rolled back?
- How does Dockerized Airflow securely invoke host-based dlt/dbt execution?
- How are pipeline ownership and lifecycle states represented?
- What ClickHouse-specific SCD2 strategy is verified for generated models?
- Which dbt artifacts and dlt metadata should be retained in MinIO?
- Which Streamlit views are necessary for the portfolio demonstration?
- Should dbt Docs be linked, embedded, or served through a shared reverse proxy?

The answers should be made after the underlying ELT and orchestration behavior
is demonstrated manually.
