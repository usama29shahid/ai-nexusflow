# AI-NexusFlow — Development Environment & Architecture

## 1. Project Overview

**AI-NexusFlow** is a modern data engineering project that will initially demonstrate an ELT architecture and will later evolve toward an AI-powered ELT/data engineering platform.

The initial objective is to build a reliable and reproducible ELT foundation before adding more advanced components such as:

* Apache Spark / PySpark
* Apache Iceberg
* Airflow
* Kafka / streaming
* RAG
* LangChain / LangGraph
* LLM-based ELT generation and automation

The project will be developed incrementally rather than introducing all technologies at once.

---

# 2. Current Architecture Decision

The most important decision made so far is to separate **infrastructure services** from **Python development dependencies**.

## Development environment

### WSL2 Ubuntu

Python applications and Python packages will run natively inside WSL2.

This includes:

* Python
* uv
* DLT
* dbt
* dbt-clickhouse
* Other Python libraries
* Project source code

### Docker

Docker will run infrastructure/services.

Currently:

* ClickHouse
* MinIO

Later:

* Spark
* Kafka
* Airflow
* Other infrastructure services as required

The architecture is therefore:

```text
Windows 11
│
├── Docker Desktop
│     │
│     └── Docker Engine
│
└── WSL2 Ubuntu
      │
      └── ~/projects/ai-nexusflow
             │
             ├── Python
             ├── uv
             ├── DLT
             ├── dbt
             ├── Source Code
             │
             └───────────────┐
                             │
                             │ network connection
                             ▼
                       Docker Compose
                             │
                       ┌─────┴─────┐
                       │           │
                       ▼           ▼
                  ClickHouse     MinIO
                  Warehouse      Object Store
```

---

# 3. Why Python/DLT/dbt Are Outside Docker During Development

We initially considered putting DLT and dbt inside Docker.

That approach works, but it introduced unnecessary development complexity.

For example, Docker created a `.venv` inside the bind-mounted WSL project directory with root ownership. This caused:

```text
Permission denied (os error 13)
```

when `uv` attempted to modify the environment from WSL.

We therefore decided:

> Python application development should happen natively in WSL, while Docker provides infrastructure.

This gives easier:

* Cursor/VS Code integration
* Python debugging
* Breakpoints
* Autocomplete
* Linting
* Testing
* Faster development iteration
* Normal `uv` workflow

The Python environment is still reproducible because dependencies are defined by:

```text
pyproject.toml
uv.lock
```

---

# 4. Production Architecture — Future Decision

Production will be handled separately.

The likely future architecture is:

```text
GitHub
   │
   ▼
CI/CD
   │
   ▼
Docker image
   │
   ├── Python
   ├── DLT
   └── dependencies
```

and similarly for dbt.

This gives production:

* Dependency isolation
* Reproducible environments
* Immutable deployment artifacts
* No manual Python installation
* Easier CI/CD
* Easier deployment to AWS or another Linux environment

However, **production containerization is not part of the current phase**.

We will revisit it when the ELT pipeline is working.

---

# 5. Technology Stack — Current Phase

| Component      | Purpose                      | Current Environment |
| -------------- | ---------------------------- | ------------------- |
| Python         | Application language         | WSL                 |
| uv             | Python dependency management | WSL                 |
| DLT            | Data ingestion               | WSL                 |
| dbt            | Transformation               | WSL                 |
| dbt-clickhouse | dbt adapter                  | WSL                 |
| ClickHouse     | Analytical warehouse         | Docker              |
| MinIO          | S3-compatible object storage | Docker              |
| Git/GitHub     | Source control               | WSL/GitHub          |
| Docker Compose | Infrastructure management    | Docker              |

---

# 6. Planned ELT Architecture

The initial target is:

```text
                    Source
                      │
                      ▼
                     DLT
                      │
              ┌───────┴────────┐
              │                │
              ▼                ▼
         ClickHouse           MinIO
         Warehouse         Object Storage
              │                │
              ▼                ▼
             dbt             Parquet
              │
              ▼
         ClickHouse
         Transformed
```

This gives two branches.

## Branch 1 — Warehouse ELT

```text
DLT
 ↓
ClickHouse
 ↓
dbt
 ↓
ClickHouse
```

## Branch 2 — Object storage / future lakehouse

```text
DLT
 ↓
MinIO
 ↓
Parquet
 ↓
Future: Iceberg
 ↓
Future: PySpark
```

This second branch will be developed later.

---

# 7. Target Multi-Branch Data Platform Architecture

The project will evolve into a **parallel multi-branch data engineering platform**.

The important architectural decision is:

> **All branches are independent implementations starting from the common ingestion layer. Branch 3, Branch 4, and Branch 5 are not children of Branch 1 or Branch 2.**

The purpose is to demonstrate how the same data engineering problem can be implemented using different warehouse, open-source lakehouse, managed Spark, and serverless/cloud technologies.

```text
                              Common Source
                                   │
                                  DLT
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │             │            │            │             │
        ▼             ▼            ▼            ▼             ▼
   BRANCH 1       BRANCH 2     BRANCH 3     BRANCH 4      BRANCH 5
   Non-Big Data   Big Data     Databricks     AWS EMR      AWS Glue
        │             │            │            │             │
        ▼             ▼            ▼            ▼             ▼
   ClickHouse      MinIO       Databricks      S3            S3
        │          Parquet         │            │             │
        ▼          Iceberg         ▼            ▼             ▼
       dbt          Spark       Spark/Delta    EMR/Spark     Glue/Spark
        │             │            │            │             │
        ▼             ▼            ▼            ▼             ▼
   ClickHouse      Iceberg    Unity Catalog   S3/Iceberg   S3/Iceberg
   transformed     tables     / Delta tables     │             │
                                                 ▼             ▼
                                              Redshift       Redshift
                                               serving        serving
```

### Branch 1 — Open-source / Non-Big-Data ELT

```text
DLT
 ↓
ClickHouse
 ↓
dbt
 ↓
ClickHouse
```

Primary purpose:

* Python/DLT ingestion
* Analytical warehouse
* SQL-based ELT
* dbt transformations
* dbt testing/documentation later

**Final transformed output:** ClickHouse.

---

### Branch 2 — Open-source Big-Data / Lakehouse

```text
DLT
 ↓
MinIO
 ↓
Parquet
 ↓
Iceberg
 ↓
Spark / PySpark
 ↓
Iceberg Gold Tables
```

Primary purpose:

* Object storage
* Parquet
* Apache Iceberg
* Open table formats
* Spark/PySpark
* Separation of storage and compute

**Final transformed output:** Iceberg tables stored in MinIO.

ClickHouse may later be used to query or consume the lake data, but it is **not the primary final destination of Branch 2**. This keeps the branch genuinely focused on an open-source lakehouse architecture.

---

### Branch 3 — Databricks Big-Data Branch

```text
DLT
 ↓
Databricks
 ↓
PySpark / Spark SQL
 ↓
Delta Lake
 ↓
Unity Catalog
 ↓
Gold Tables
```

Primary purpose:

* Databricks platform
* Distributed processing with Spark
* PySpark
* Spark SQL
* Delta Lake
* Unity Catalog
* Managed lakehouse capabilities

**Final transformed output:** Delta tables managed/cataloged through Unity Catalog.

PostgreSQL and ClickHouse are **not** the primary destinations for this branch. The goal is to demonstrate the Databricks-native lakehouse pattern:

```text
Compute  → Databricks / Spark
Storage  → Delta Lake
Catalog  → Unity Catalog
```

---

### Branch 4 — AWS EMR Big-Data Branch

```text
DLT
 ↓
S3
 ↓
EMR
 ↓
PySpark
 ↓
Iceberg / Parquet
 ↓
S3
 ↓
Optional Redshift serving layer
```

Primary purpose:

* AWS-managed Spark
* EMR
* PySpark
* S3
* Open data formats/table formats
* Lake + warehouse serving pattern

The primary lake output remains in S3. Redshift can be used as an analytical serving layer when appropriate.

---

### Branch 5 — AWS Glue / Serverless ETL Branch

```text
DLT
 ↓
S3
 ↓
AWS Glue
 ↓
Spark
 ↓
Iceberg / Parquet
 ↓
S3
 ↓
Optional Redshift serving layer
```

Primary purpose:

* AWS Glue
* Serverless ETL
* Managed Spark
* S3
* Iceberg/Parquet
* AWS-native data integration

The primary lake output remains in S3, while Redshift can optionally provide a warehouse/serving layer.

---

## Final Branch Comparison

| Branch | Focus | Compute | Primary Storage / Table Format | Final / Serving Output |
| --- | --- | --- | --- | --- |
| **1** | Non-Big-Data ELT | DLT + dbt | ClickHouse | **ClickHouse** |
| **2** | Open-source Big Data | Spark/PySpark | MinIO + Parquet/Iceberg | **Iceberg / MinIO** |
| **3** | Databricks Big Data | Databricks + Spark | Delta Lake + Unity Catalog | **Delta / Databricks** |
| **4** | AWS Managed Spark | EMR + PySpark | S3 + Iceberg/Parquet | **S3 + optional Redshift** |
| **5** | AWS Serverless ETL | Glue + Spark | S3 + Iceberg/Parquet | **S3 + optional Redshift** |

### Architecture principle

The project is intentionally **not** trying to force every branch into the same destination.

Instead, each branch demonstrates a different architectural pattern:

```text
Branch 1 → Warehouse-centric ELT
Branch 2 → Open-source lakehouse
Branch 3 → Databricks lakehouse
Branch 4 → AWS managed Spark
Branch 5 → AWS serverless Spark ETL
```

This makes the project useful not only as an implementation but also as a technology-comparison and architecture-learning platform.

---

# 8. Cross-Cutting Orchestration and Future Capabilities

The five branches remain parallel. Orchestration and other capabilities sit across them.

## Airflow

Later:

```text
                         Airflow
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
       Branch 1          Branch 2         Branch 3/4/5
        DLT/dbt          Spark/Iceberg     Cloud jobs
```

Airflow is therefore an orchestration layer, not another data-processing branch.

## Streaming

Eventually:

```text
Kafka
  ↓
Spark Streaming
  ↓
Iceberg / Delta / ClickHouse
```

Streaming will be added only when the batch architecture is stable.

## Serverless

Serverless is primarily demonstrated through **AWS Glue**, while Databricks can later be evaluated for its own serverless compute capabilities.

It should be treated as a **compute/deployment characteristic**, not as a sixth data branch.


---

# 8. Repository

The GitHub repository is:

```text
ai-nexusflow
```

The local repository is:

```text
~/projects/ai-nexusflow
```

Current conceptual structure:

```text
ai-nexusflow/
│
├── docker-compose.yml
├── .env
├── .gitignore
│
└── app/
    ├── pyproject.toml
    ├── uv.lock
    │
    ├── ingestion/
    │   └── DLT pipelines
    │
    └── nexus_dbt/
        ├── dbt_project.yml
        ├── models/
        ├── macros/
        ├── seeds/
        ├── snapshots/
        └── tests/
```

The dbt project structure is generated using:

```bash
dbt init nexus_dbt
```

rather than manually creating dbt directories.

---

# 9. Python Dependency Management

`uv` is the Python dependency manager.

The important files are:

```text
pyproject.toml
uv.lock
```

`pyproject.toml` defines project dependencies.

`uv.lock` records the resolved dependency versions.

The normal development workflow is:

```bash
cd ~/projects/ai-nexusflow/app

uv sync
```

Then execute tools through:

```bash
uv run
```

Examples:

```bash
uv run python --version
uv run dlt --version
uv run dbt --version
```

---

# 10. Verified Development Environment

The environment has been successfully verified.

Current verified versions:

```text
Python          3.12.12
DLT             1.30.0
dbt-core        1.11.13
dbt-clickhouse  1.10.2
```

Verification commands:

```bash
uv run python --version
uv run dlt --version
uv run dbt --version
```

The dbt version displayed an update notification, but upgrading was deliberately deferred.

The current environment is considered valid and working.

---

# 11. Docker Infrastructure

Docker Compose is responsible for infrastructure.

Current services:

```text
ClickHouse
MinIO
```

ClickHouse is exposed to WSL through:

```text
localhost:8123
```

ClickHouse native protocol:

```text
localhost:9000
```

MinIO API:

```text
localhost:9002
```

MinIO Console:

```text
localhost:9001
```

Inside Docker networking, services use their Compose service names.

For example:

```text
clickhouse:8123
minio:9000
```

This distinction is important.

From WSL:

```text
localhost:8123
localhost:9002
```

From another Docker container:

```text
clickhouse:8123
minio:9000
```

---

# 12. Environment Variables

Environment-specific configuration is stored in:

```text
.env
```

Example:

```env
CLICKHOUSE_DB=warehouse
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=

CLICKHOUSE_HTTP_PORT=8123
CLICKHOUSE_NATIVE_PORT=9000

MINIO_API_PORT=9002
MINIO_CONSOLE_PORT=9001

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
```

`.env` must not be committed to GitHub.

Therefore:

```text
.env
```

must be included in:

```text
.gitignore
```

The goal is eventually:

```text
Clone repository
       ↓
Create/provide .env
       ↓
Start infrastructure
       ↓
Run application
```

This allows the project to be moved between development and future deployment environments without hardcoding credentials/configuration.

---

# 13. Docker Desktop + WSL2

The development machine is:

```text
Windows 11
+
WSL2 Ubuntu
+
Docker Desktop
```

Docker Desktop's WSL integration must be enabled for the Ubuntu distribution.

Verification:

```bash
docker --version
docker compose version
```

Docker test:

```bash
docker run hello-world
```

---

# 14. Docker Compose Commands

From:

```text
~/projects/ai-nexusflow
```

Start infrastructure:

```bash
docker compose up -d
```

Check services:

```bash
docker compose ps
```

Stop services:

```bash
docker compose down
```

Validate Compose configuration:

```bash
docker compose config
```

View logs:

```bash
docker compose logs
```

View a specific service:

```bash
docker compose logs clickhouse
```

---

# 15. Infrastructure Verification

## ClickHouse

```bash
curl http://localhost:8123/ping
```

Expected:

```text
Ok.
```

## MinIO

Open:

```text
http://localhost:9001
```

Use the credentials defined in `.env`.

---

# 16. Important Problem We Encountered

### Problem

Docker was previously mounting:

```text
./app:/app
```

and running:

```bash
uv sync
```

inside the container.

This caused Docker to create:

```text
app/.venv
```

with root ownership.

Then WSL `uv` produced:

```text
Permission denied (os error 13)
```

Example:

```text
failed to open file
.../app/.venv/CACHEDIR.TAG
Permission denied
```

### Resolution

We removed the Docker-created virtual environment:

```bash
sudo rm -rf ~/projects/ai-nexusflow/app/.venv
```

Then recreated it using the WSL user:

```bash
cd ~/projects/ai-nexusflow/app
uv sync
```

The local environment then worked correctly.

### Lesson

Do not mix ownership of the same `.venv` between Docker/root and the WSL developer environment.

The current architecture avoids this by keeping the Python development environment in WSL.

---

# 17. Another Problem — Docker Was Not Available in WSL

Initially:

```text
The command 'docker' could not be found in this WSL 2 distro.
```

The resolution was to enable:

```text
Docker Desktop
→ Settings
→ Resources
→ WSL Integration
→ Ubuntu
```

After enabling WSL integration, Docker became available from Ubuntu.

---

# 18. Important Architecture Principle

The project follows this principle:

> **Infrastructure is containerized; application development is native to WSL.**

Therefore:

```text
Docker:
  ClickHouse
  MinIO
  future infrastructure

WSL:
  Python
  DLT
  dbt
  application code
  development tools
```

This is intentionally different from the eventual production architecture.

---

# 19. Development Workflow

The intended daily workflow is:

### Start infrastructure

```bash
cd ~/projects/ai-nexusflow
docker compose up -d
```

### Enter application directory

```bash
cd app
```

### Synchronize Python dependencies

```bash
uv sync
```

### Develop DLT

```bash
uv run python ingestion/<pipeline>.py
```

### Run dbt

```bash
uv run dbt run
```

### Run dbt tests

```bash
uv run dbt test
```

### Stop infrastructure when finished

```bash
cd ..
docker compose down
```

---

# 20. Git Workflow

Source code and configuration belong in Git.

Commit:

```text
pyproject.toml
uv.lock
docker-compose.yml
.gitignore
Python source
dbt project
dbt models
documentation
```

Do not commit:

```text
.env
.venv/
__pycache__/
dbt logs
temporary files
secrets
```

Typical workflow:

```bash
git status
git add .
git commit -m "Description"
git push origin main
```

---

# 21. Future ELT Generator / LLM Agent

The project is intentionally being designed so that it can later become an **LLM-powered ELT generator**.

The future agent may generate or modify:

```text
DLT pipeline code
        ↓
Source configuration

dbt models
        ↓
Transformation logic

dbt tests
        ↓
Data quality

Python code
        ↓
Custom transformations

Docker/configuration
        ↓
Environment setup
```

Potential future flow:

```text
User requirement
       ↓
LLM / Agent
       ↓
Understand source
       ↓
Generate DLT ingestion
       ↓
Generate dbt models
       ↓
Generate tests
       ↓
Run validation
       ↓
Execute ELT
       ↓
Validate results
       ↓
Report outcome
```

This is a future layer.

The immediate priority is to make the underlying ELT platform reliable first.

---

# 24. Agreed Development Roadmap

The roadmap follows the principle of **one stable foundation first, then parallel technology branches**.

## Phase 1 — Core Open-source ELT

```text
Python
uv
DLT
dbt
ClickHouse
MinIO
Docker Compose
GitHub
```

Goal:

```text
                    DLT
                     │
              ┌──────┴──────┐
              ▼             ▼
         ClickHouse       MinIO
              │          Parquet
              ▼
             dbt
              │
              ▼
         ClickHouse
```

The immediate objective is to make this simple ELT foundation reliable.

## Phase 2 — Open-source Big Data Branch

Add:

```text
PySpark
Apache Iceberg
```

Goal:

```text
DLT
 ↓
MinIO
 ↓
Parquet
 ↓
Iceberg
 ↓
PySpark
 ↓
Iceberg Gold Tables
```

This branch demonstrates an open-source lakehouse without requiring Databricks.

## Phase 3 — Databricks Branch

Add:

```text
Databricks
PySpark
Delta Lake
Unity Catalog
```

Goal:

```text
DLT
 ↓
Databricks
 ↓
Spark / PySpark
 ↓
Delta Lake
 ↓
Unity Catalog
 ↓
Gold Tables
```

This branch is independent of Branch 1 and Branch 2.

## Phase 4 — AWS EMR Branch

Add:

```text
AWS S3
AWS EMR
PySpark
Iceberg
```

Goal:

```text
DLT
 ↓
S3
 ↓
EMR
 ↓
PySpark
 ↓
Iceberg / Parquet
 ↓
S3
```

Optional Redshift serving can be added later.

## Phase 5 — AWS Glue Branch

Add:

```text
AWS Glue
S3
Spark
Iceberg
```

Goal:

```text
DLT
 ↓
S3
 ↓
AWS Glue
 ↓
Spark
 ↓
Iceberg / Parquet
 ↓
S3
```

Optional Redshift serving can be added later.

## Phase 6 — Orchestration

Add:

```text
Airflow
```

to orchestrate the independent branches.

## Phase 7 — Streaming

Add:

```text
Kafka
Spark Streaming
```

when the batch architecture is stable.

## Phase 8 — AI / LLM Layer

Add:

```text
RAG
LangChain
LangGraph
LLM agents
```

for intelligent ELT generation, automation, validation, and operational assistance.


---

# 25. Current Status

### Completed

* [x] GitHub repository created: `ai-nexusflow`
* [x] Repository cloned into WSL
* [x] WSL2 development environment configured
* [x] Docker Desktop WSL integration configured
* [x] Docker Compose configuration established
* [x] ClickHouse container configured
* [x] MinIO container configured
* [x] Python project initialized with uv
* [x] DLT dependency installed
* [x] dbt-core installed
* [x] dbt-clickhouse installed
* [x] dbt project initialized as `nexus_dbt`
* [x] `pyproject.toml` created
* [x] `uv.lock` created
* [x] Python/DLT/dbt versions verified
* [x] `.venv` permission issue identified and resolved
* [x] Development architecture clarified

### Current versions

```text
Python          3.12.12
DLT             1.30.0
dbt-core        1.11.13
dbt-clickhouse  1.10.2
```

### Not implemented yet

* [ ] Actual DLT ingestion pipeline
* [ ] ClickHouse source/target configuration
* [ ] MinIO data ingestion
* [ ] Parquet generation
* [ ] dbt models
* [ ] dbt tests
* [ ] PySpark / Apache Iceberg — Branch 2
* [ ] Databricks / Delta / Unity Catalog — Branch 3
* [ ] AWS EMR / PySpark — Branch 4
* [ ] AWS Glue / Spark — Branch 5
* [ ] Airflow
* [ ] Kafka
* [ ] LLM ELT generator

---

# 26. Immediate Next Step

Do **not** add Spark, Iceberg, Airflow, RAG, or agents yet.

The next engineering milestone is:

```text
Source
  ↓
DLT
  ├──→ ClickHouse
  │
  └──→ MinIO
```

Then verify the data.

After that:

```text
ClickHouse
   ↓
dbt
   ↓
transformed ClickHouse tables
```

Only after this simple ELT pipeline works reliably should the architecture be expanded.

The guiding principle for the project is:

> **Build a simple, working ELT foundation first. Add advanced technologies only when the foundation is stable and the new technology has a clear purpose.**