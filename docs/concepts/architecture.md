# Architecture

Scythe is organized into three layers: a **User Layer** that researchers interact with directly, a **Core Layer** that implements the experiment orchestration logic, and an **Infrastructure Layer** that provides the execution and storage backends.

## Three-Layer Overview

```mermaid
block-beta
    columns 1
    block:user["User Layer"]
        A["ExperimentInputSpec / ExperimentOutputSpec"]
        B["@ExperimentRegistry.Register()"]
        C["BaseExperiment.allocate()"]
    end
    block:core["Scythe Core"]
        D["registry"] E["experiments"] F["scatter_gather"] G["base"] H["worker"]
    end
    block:infra["Infrastructure Layer"]
        I["Hatchet SDK"] J["S3 / boto3"] K["Docker / ECS"] L["SST / Pulumi"]
    end
    user --> core
    core --> infra
```

### User Layer

The user layer is what researchers and engineers interact with. It consists of three steps:

1. **Define schemas** -- Subclass `ExperimentInputSpec` and `ExperimentOutputSpec` with typed Pydantic fields that describe the inputs and outputs of a single simulation run.
2. **Register the experiment** -- Decorate your simulation function with `@ExperimentRegistry.Register()`, which wraps it in Hatchet task middleware.
3. **Allocate and run** -- Create a `BaseExperiment` and call `.allocate(specs, version=...)` to launch the experiment on a pool of workers.

No knowledge of queues, S3, serialization, or container orchestration is required.

### Core Layer

The core layer is composed of five modules that implement experiment orchestration:

| Module           | Responsibility                                                                                                                                                                   |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `base`           | `ExperimentInputSpec`, `ExperimentOutputSpec`, `BaseSpec` -- schema base classes with file reference handling, MultiIndex construction, scalar extraction, and artifact transfer |
| `registry`       | `ExperimentRegistry` -- decorator that wraps user functions in Hatchet tasks with pre/post middleware (artifact fetch, temp directory, S3 upload, DataFrame serialization)       |
| `experiments`    | `BaseExperiment`, `VersionedExperiment`, `ExperimentRun`, `SemVer` -- allocation, versioning, S3 layout, manifest generation, and result retrieval                               |
| `scatter_gather` | `ScatterGatherInput`, `RecursionMap`, `ScatterGatherResult` -- recursive fan-out/fan-in workflow with grid-stride partitioning and Parquet-based payload transfer                |
| `worker`         | `ScytheWorkerConfig` -- worker configuration with role flags (`DOES_FAN`, `DOES_LEAF`), affinity labels, and environment-aware naming                                            |

### Infrastructure Layer

Scythe delegates execution and storage to external systems:

- **Hatchet** -- The distributed task engine that handles workflow scheduling, retries, durable execution, and worker coordination.
- **S3 (via boto3)** -- Object storage for experiment specs, input artifacts, intermediate scatter/gather payloads, and final result Parquet files.
- **Docker / ECS** -- Containerization and orchestration of worker processes, from local Docker Compose to AWS ECS with Fargate spot capacity.
- **SST / Pulumi** -- Infrastructure-as-code tools for provisioning cloud resources (VPCs, clusters, services, buckets).

## Data Flow

The following diagram shows how data moves through the system during an experiment:

```mermaid
sequenceDiagram
    participant User
    participant Scythe as Scythe Core
    participant Hatchet
    participant S3
    participant Workers

    User->>Scythe: allocate(specs, version)
    Scythe->>S3: Upload specs.pq, artifacts, manifest
    Scythe->>Hatchet: Trigger scatter/gather workflow
    Hatchet->>Workers: Dispatch scatter/gather task
    Workers->>S3: Fetch specs, split into sub-batches
    Workers->>Hatchet: Spawn child tasks (recurse or leaf)
    Hatchet->>Workers: Dispatch leaf experiment tasks
    Workers->>S3: Fetch input artifacts
    Workers->>Workers: Run simulation function
    Workers->>S3: Upload output files, DataFrames
    Workers->>Hatchet: Return result
    Hatchet->>Workers: Gather results at scatter/gather nodes
    Workers->>S3: Write final/ scalars.pq, result_file_refs.pq
    User->>S3: Download results
```

## Module Dependency Graph

```mermaid
flowchart TD
    base --> settings
    base --> utils_filesys["utils.filesys"]
    base --> utils_results["utils.results"]
    registry --> base
    registry --> hatchet_mod["hatchet"]
    registry --> settings
    registry --> utils_s3["utils.s3"]
    scatter_gather --> base
    scatter_gather --> registry
    scatter_gather --> hatchet_mod
    scatter_gather --> settings
    scatter_gather --> utils_filesys
    scatter_gather --> utils_results
    scatter_gather --> utils_s3
    experiments --> registry
    experiments --> scatter_gather
    experiments --> settings
    experiments --> utils_filesys
    experiments --> utils_results
    experiments --> utils_s3
    worker --> hatchet_mod
    worker --> registry
    worker --> scatter_gather
```
