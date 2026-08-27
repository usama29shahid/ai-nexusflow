# GitHub REST API ingestion standard

This document is the single source of truth for ingesting GitHub REST API data through AI-NexusFlow capabilities.

It defines:

- GitHub endpoint meaning and data grain
- Common dlt extraction rules
- Authentication, pagination, retries, rate limits, and incremental behavior
- Branch-specific archive, Bronze, and transformation contracts
- Rules for future LLM-generated ingestion artifacts

The GitHub source is external and read-only from AI-NexusFlow's perspective. This project does not manage GitHub repositories, create pull requests, operate GitHub Actions, or administer deployments.

This document defines source semantics once. Each execution branch still owns its own dlt and transformation implementation.

## Related standards

- [Architecture](architecture.md)
- [dlt extraction](dlt-extraction.md)
- [dlt_dbt_clickhouse](dlt-dbt-clickhouse.md)
- [dlt_dbt_spark_iceberg](dlt-dbt-spark-iceberg.md)
- [Environments](environments.md)
- [Observability](observability.md)
- [dbt modeling](dbt-modeling.md)

Official GitHub references:

- [REST API overview](https://docs.github.com/en/rest)
- [Authentication](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api)
- [Fine-grained personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
- [REST API pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api)
- [REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [Commits endpoint](https://docs.github.com/en/rest/commits/commits)
- [Pull requests endpoint](https://docs.github.com/en/rest/pulls/pulls)
- [Issues endpoint](https://docs.github.com/en/rest/issues/issues)

## 1. Source contract

### API and inputs

| Item | Contract |
|---|---|
| API | GitHub REST API |
| Base URL | `https://api.github.com` |
| Repository identity | `owner` and `repo` path parameters |
| Authentication | Bearer token from environment or secret configuration |
| Token | Read-only fine-grained personal access token during local development |
| API version | Explicit `X-GitHub-Api-Version` request header, pinned and updated deliberately |
| Response media type | GitHub's JSON media type |
| Local environment | `NEXUS_ENV=dev` by default |
| Local run identity | A new shared `NEXUS_RUN_ID` for each load |

Credentials must never be hardcoded or committed. The source configuration must fail clearly when a required token or repository identifier is absent.

One configured repository is the initial execution scope. Repository identifiers are parameters to the same endpoint contract; they are not separate endpoint resources, tables, Gold models, or archive variants.

Multiple-repository incremental execution requires repository-scoped dlt state. It must not share one cursor across repositories. Multi-repository execution is an extension of this standard, not an assumption for the first implementation.

### Endpoint, resource, job, and table

These terms have different meanings:

| Term | Meaning |
|---|---|
| Source | GitHub, the external API |
| Endpoint | A GitHub REST API contract, such as `/repos/{owner}/{repo}/commits` |
| dlt resource | The extraction/load representation of one endpoint |
| Job | The executable dlt script or later Airflow task for that endpoint |
| Table | The Bronze representation of the endpoint resource |
| Repository parameter | The `owner` and `repo` values used with an endpoint |

The dlt unit is one endpoint resource: **one script per endpoint**. A different repository value does not automatically create another resource. A separate resource, script, and Bronze table are justified only when the payload schema, grain, authentication, or incremental behavior differs.

#### Canonical naming

Script name, dlt resource name, Bronze table name, archive `{endpoint}` segment, and dbt `source()` table name use the **same** resource identifier. Do not use opaque job names such as `pipe_one`.

| Resource | Script (when implemented) | Bronze table | Archive segment | Airflow task id (Phase 2) |
|---|---|---|---|---|
| `commits` | `commits.py` | `commits` | `github/commits/...` | `github_commits` |
| `pull_requests` | `pull_requests.py` | `pull_requests` | `github/pull_requests/...` | `github_pull_requests` |
| `issues` | `issues.py` | `issues` | `github/issues/...` | `github_issues` |

ClickHouse layout when implemented:

```text
branches/dlt_dbt_clickhouse/dlt/github/
  commits.py
  pull_requests.py
  issues.py
```

#### Parameters vs separate pipelines

| Case | Rule |
|---|---|
| Same endpoint contract, different URL parameters (`owner` / `repo`) | One script and one Bronze table. Pass parameters into the job. Later Airflow may run multiple tasks that call the same script with different params. |
| Incremental cursors across repositories | Keep dlt state repository-scoped; do not share one `since` cursor across repos. |
| Same URL shape but different payload contract (schema, grain, auth, or incremental) | New script, new resource, new Bronze table, and a catalog update in this document. |
| `owner` / `repo` as archive folders | Never. Repository identity is a parameter and row metadata, not a `{param_variant}` archive segment. |

### Responsibility boundary

```text
GitHub REST API
  → dlt extraction and loading
  → branch-specific raw archive and Bronze   ← dlt work ends here
  → branch transformation engine (dbt)       ← staging through Gold / marts
  → branch serving layer
```

dlt owns authentication, pagination, retries, rate limits, incremental state, schema tracking, archive writing, Bronze loading, and ingestion telemetry. **dlt stops at the MinIO JSONL archive and Bronze.** It does not own staging, intermediate, Gold, marts, or published models.

The branch transformation layer (dbt) owns typing, flattening, classification, deduplication, relationships, business rules, tests, Gold models, and marts. dbt must not call GitHub.

## 2. Common v1 endpoint catalog

The initial endpoint set is deliberately small. Add an endpoint when a real Gold, fact, event, or mart requirement justifies it; do not ingest every GitHub API collection by default.

| Resource | Endpoint | Response grain | Initial loading strategy | Bronze table name |
|---|---|---|---|---|
| `commits` | `GET /repos/{owner}/{repo}/commits` | One commit for one repository | Incremental with GitHub-supported `since` | `commits` |
| `pull_requests` | `GET /repos/{owner}/{repo}/pulls` | One pull request for one repository | Full-refresh snapshot for v1 | `pull_requests` |
| `issues` | `GET /repos/{owner}/{repo}/issues` | One issue or pull-request issue representation for one repository | Incremental with GitHub-supported `since` | `issues` |

### Commits

The commits endpoint represents repository commit history. The stable business identity is the repository identity plus commit SHA. The response can contain nested author, committer, commit message, tree, and parent information; Bronze should preserve that structure as far as dlt normalization allows.

GitHub supports a `since` time boundary. dlt owns the persisted extraction state. A timestamp overlap may be used at the boundary so records sharing a timestamp are not missed. Duplicate historical rows are acceptable in append-only Bronze and are resolved downstream by business key and timestamp.

### Pull requests

The pull-request endpoint represents the lifecycle of pull requests opened against the configured repository. The stable business identity is repository identity plus pull-request number.

For v1, pull requests use a full-refresh snapshot. This avoids inventing an unsafe incremental stop condition for an endpoint that does not provide the same `since` contract as issues and commits. Every extraction still appends to Bronze with a new run ID. Downstream models select the latest record for current-state views and retain historical loads when required.

The endpoint may include nested user, branch, repository, and link objects. Preserve the raw response; flatten only in the branch transformation layer.

### Issues

The issues endpoint represents GitHub's issue collection, but GitHub treats pull requests as issues for this API. A response can therefore contain both ordinary issues and pull-request representations.

The raw `issues` Bronze table must preserve both response types. Downstream staging derives a pull-request indicator from the presence of the `pull_request` field and produces issue-only relations by excluding those records where required.

The stable business identity is repository identity plus issue number. GitHub supports a `since` time boundary for updated issues. dlt owns the state and may use a timestamp overlap at the boundary.

### Deferred endpoints

The following are not part of the v1 extraction requirement:

- Repository metadata
- Issue comments
- Pull-request reviews
- Releases
- Contributors
- Branches
- Repository topics
- Actions workflow runs
- Organization repository discovery
- Authenticated-user repository discovery

They may be added through the extension process when a consumer requirement needs them.

## 3. Common dlt ingestion rules

These rules apply to every branch that implements GitHub ingestion.

### Extract once, load to configured destinations

The API response is extracted once. The same extraction feeds the branch's configured raw archive and Bronze destination. The archive and Bronze load must not make separate GitHub requests.

### dlt owns extraction concerns

dlt is responsible for:

- REST authentication
- Request headers
- Pagination
- HTTP retries
- Rate-limit behavior
- Incremental cursors and state
- Schema tracking
- Raw archive writing
- Bronze loading
- dlt load telemetry and system tables

Do not introduce a custom pagination loop, watermark table, retry daemon, or logging platform.

### Run ID and metadata

One new shared run ID is created or received for a complete execution. The same value is passed to every endpoint load and later to the branch transformation run.

Every Bronze load should carry at least:

| Metadata | Meaning |
|---|---|
| `run_id` or `_ingest_run_id` | Shared AI-NexusFlow execution identity |
| `_extracted_at` | UTC time of extraction |
| Repository identity | The configured owner/repository context |
| Endpoint/resource identity | The GitHub resource that produced the row |
| `_dlt_*` metadata | dlt package and load telemetry |

The exact dlt system-column names remain dlt-owned. Do not replace dlt metadata with a custom telemetry system.

### Append-only history and replay

Bronze and archive data are append-only. Incremental extraction reduces API volume; it does not update or delete historical Bronze rows.

Replay reads an existing archive prefix without calling GitHub, loads Bronze with a new run ID, and then runs the branch transformation layer. Existing archive objects and Bronze rows are not mutated.

## 4. Pagination, retries, and rate limits

### Pagination

GitHub exposes pagination through response `Link` headers. The dlt resource declares and follows the `rel="next"` link until GitHub does not provide another page.

For the selected list endpoints, request `per_page=100`, the documented maximum page size. Completion must be determined by the absence of the next link or the endpoint's normal empty-page behavior, not by a hardcoded page count.

Do not hand-roll endpoint-specific page loops unless GitHub introduces a nonstandard contract and this document is updated first.

### Retries

Retry transient connection failures and server-side 5xx responses with bounded exponential backoff. Honor `Retry-After` when present.

Do not retry indefinitely. Ordinary 401, permission-related 403, 404, and 422 responses indicate configuration, authorization, or request problems and should fail clearly.

A 403 response accompanied by GitHub rate-limit headers is handled as rate limiting: use the reset information or documented delay before making another request. A normal permission-related 403 must not be treated as a transient failure.

dlt HTTP retries and future Airflow task retries are separate concerns. Airflow is not part of this Phase 1 implementation.

### Rate limits

The source should use authenticated requests for predictable limits, avoid unnecessary endpoint calls, and expose useful rate-limit information in dlt/native logs. It must not build a separate rate-limit service.

## 5. Common incremental policy

| Endpoint | V1 policy | Reason |
|---|---|---|
| Commits | Incremental using `since` | GitHub supports a source-side time boundary |
| Issues | Incremental using `since` | GitHub supports a source-side updated-time boundary |
| Pull requests | Full refresh | V1 avoids an unsafe custom incremental filter |

dlt stores incremental state by its normal pipeline/resource state mechanism. No custom checkpoint or watermark database is allowed.

Timestamp overlap is permitted at a boundary to reduce the risk of missing records with equal or late timestamps. Because Bronze is append-only, downstream staging must use declared business keys and timestamps when it creates current-state relations.

ETags, conditional requests, and other request-cache strategies are deferred until the basic extraction path is verified.

## 6. Branch contract matrix

Common GitHub endpoint semantics apply to every branch, but physical storage and transformation behavior are branch-specific.

| Branch | Archive | Bronze destination | Transformation | Serving layer | Status |
|---|---|---|---|---|---|
| `dlt_dbt_clickhouse` | `nexus-dlt-dbt-clickhouse-{env}` | ClickHouse `raw_github_{env}` | dbt-clickhouse | ClickHouse Gold/marts | Current priority |
| `dlt_dbt_spark_iceberg` | `nexus-dlt-dbt-spark-iceberg-archive-{env}` | Polaris/Iceberg `nexus_{env}.raw_github` | dbt-spark | Iceberg/Trino | Independent capability |
| `branch_3_databricks` | Defined when implemented | Defined when implemented | Databricks/Spark | Delta/Databricks | Future |
| `branch_4_emr` | Defined when implemented | Defined when implemented | EMR/PySpark | S3/Iceberg or optional Redshift | Future |
| `branch_5_glue` | Defined when implemented | Defined when implemented | Glue/Spark | S3/Iceberg or optional Redshift | Future |

Branches must not read another branch's Bronze tables as their implementation. A disabled branch must never be selected or executed. Future rows in this matrix are design placeholders and do not authorize speculative implementation.

## 7. `dlt_dbt_clickhouse` profile

This is the current implementation priority.

```text
GitHub REST API
  → dlt
  → MinIO JSONL raw archive
  → ClickHouse raw_github_{env}
  → dbt staging stg_github_{env}
  → shared int/gold/marts databases
```

| Surface | Contract |
|---|---|
| Archive bucket | `nexus-dlt-dbt-clickhouse-{env}` |
| Archive prefix | `github/{endpoint}/dt=YYYY-MM-DD/run_id={run_id}/` |
| Bronze database | `raw_github_{env}` |
| Staging database | `stg_github_{env}` |
| Shared intermediate database | `int_{env}` |
| Shared Gold database | `gold_{env}` |
| Optional marts database | `marts_{env}` |

`{endpoint}` is the canonical resource name (`commits`, `pull_requests`, `issues`). GitHub `owner` / `repo` parameters do not add a `{param_variant}` path segment under that prefix. The general archive key template in [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md) still allows `{param_variant}` for other sources when the **payload contract** differs; that case does not apply to repository identity for GitHub.

The ClickHouse branch must not create `gold_github_{env}`. Gold is shared and is organized by grain (`dim_*`, `fct_*`, `evt_*`), not by API source.

dbt reads the GitHub Bronze tables through `source()`. It owns issue/pull-request classification, flattening, typing, deduplication, relationships, and tests. Gold models and marts are requirement-driven; endpoint names do not automatically create Gold tables.

## 8. `dlt_dbt_spark_iceberg` profile

This branch is independent from the ClickHouse branch:

```text
GitHub REST API
  → dlt
  → MinIO archive
  → Iceberg Bronze through Polaris
  → dbt-spark
  → Trino
```

Its archive is separate from the ClickHouse archive. Its Bronze contract is `nexus_{env}.raw_github`, and its transformation and serving contracts are dbt-spark and Trino respectively.

The same GitHub endpoint meanings, authentication, pagination, retry, rate-limit, incremental, and run-ID rules apply. Physical names, destinations, and transformations differ. No code or Bronze table from `dlt_dbt_clickhouse` is assumed to be reusable by this branch.

## 9. Future LLM agent contract

An LLM agent generating GitHub ingestion artifacts must read this document before planning or writing artifacts.

The agent must:

- Confirm the requested destination and enabled branch.
- Select only endpoints justified by the user's requirement.
- Apply the common dlt rules.
- Apply the selected branch profile.
- Reject disabled branches.
- Preserve raw API data before analytical transformation.
- Use repository identifiers as parameters, not separate endpoint contracts.
- Name scripts and Bronze tables after the resource (`commits.py` / `commits`); never invent opaque names such as `pipe_one`.
- Stop dlt at archive + Bronze; leave staging and Gold to dbt.
- Avoid inventing unsupported incremental mechanisms.
- Avoid creating Gold models automatically from endpoint names.
- Avoid branch-crossing dependencies.
- Report unresolved permissions, incremental limitations, or unavailable destinations.

The agent's design output must contain:

```text
selected branch
selected endpoints
endpoint grain
script and Bronze table names
parameter strategy (same-contract params vs new pipeline)
authentication requirements
pagination strategy
incremental strategy
archive destination
Bronze destination
transformation destination
validation requirements
```

## 10. Extension process

When a new GitHub endpoint is needed:

1. Add its meaning and grain to the common endpoint catalog.
2. Define its pagination and incremental behavior from official GitHub documentation.
3. Explain why an existing endpoint is insufficient.
4. Define branch-specific destinations only where they differ from the existing branch contract.
5. Avoid new Gold dimensions unless the requirement names them.
6. Update the relevant branch README and tests when implementation begins.
7. Keep unsupported future branches marked as unimplemented.

An endpoint may be added to this document before implementation, but it must be labeled as planned or deferred. Documentation must not imply that an unimplemented branch or resource is runnable.

## 11. Design acceptance criteria

This standard is complete when it:

- Is the single GitHub ingestion reference for all branches.
- Separates common source rules from branch-specific contracts.
- Defines the three initial endpoints and their meanings.
- Defines authentication, pagination, retries, rate limits, and incremental state.
- Defines MinIO, Bronze, staging, Gold, and mart destinations for implemented branches.
- Preserves branch independence.
- Includes rules suitable for future LLM-generated artifacts.
- Defines canonical script, table, archive, and Airflow task naming (no opaque `pipe_one` names).
- Defines parameter grain: same-contract params share one table; different payload contracts get separate pipelines and tables.
- States that dlt ends at archive + Bronze and that post-Bronze work is dbt-only.
- Contains design only, not implementation code.
- Does not add speculative implementations for future branches.
- Links to the existing architecture, extraction, environment, observability, and modeling standards.
