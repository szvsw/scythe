# Scythe

**Scythe** is a lightweight Python library for running embarrassingly parallel experiments at scale using [Hatchet](https://hatchet.run), an open-source distributed task engine.

Researchers and engineers can define typed input/output schemas, register simulation functions, and launch millions of parallel tasks -- without writing any queue, serialization, or cloud infrastructure code.

---

## Key Features

- **Schema-driven experiments** -- Define your inputs and outputs as [Pydantic](https://docs.pydantic.dev/) models with full validation, type safety, and auto-generated JSON Schema documentation.
- **Automatic artifact handling** -- Local files referenced in your specs are automatically uploaded to S3 on allocation; output files are uploaded when each task completes.
- **Recursive scatter/gather** -- Scale from tens to millions of tasks using a configurable tree of scatter/gather nodes that parallelize both dispatch and result collection.
- **Versioned experiment runs** -- Each allocation is scoped by semantic version and timestamp, creating a reproducible record of every experiment in your S3 bucket.
- **Structured result aggregation** -- Scalar outputs, file references, and user-defined DataFrames are automatically collected into Parquet files with a MultiIndex built from your input specs.
- **Standalone and Workflow runnables** -- Register single-function experiments with `@ExperimentRegistry.Register()`, or multi-step Hatchet `Workflow` pipelines with `ExperimentRegistry.Include()`. Allocate a batch for scatter/gather, or a single spec for a versioned one-off run.
- **Flexible worker pools** -- Configure workers with role flags (leaf vs. fan), typed affinity labels (`ScytheWorkerLabel`), and environment-based slot counts.
- **Multiple deployment targets** -- Run locally with Docker Compose, on a lab cluster, or at cloud scale on AWS ECS with spot capacity.

## How It Works

Scythe wraps your simulation function in Hatchet task middleware that handles artifact transfer, temporary directories, result serialization, and S3 upload. When you allocate an experiment, Scythe validates your specs, uploads input artifacts, and triggers a scatter/gather workflow that fans out individual tasks to a pool of workers.

```mermaid
flowchart LR
    A["Define Schemas"] --> B["Register Experiment"]
    B --> C["Allocate"]
    C --> D["Scatter/Gather"]
    D --> E["Worker Pool"]
    E --> F["Results in S3"]
```

## Quick Links

| Resource             | Link                                                                                                                                                                       |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Getting Started      | [Installation](getting-started/installation.md) / [Quickstart](getting-started/quickstart.md)                                                                              |
| Concepts             | [Architecture](concepts/architecture.md) / [Scatter/Gather](concepts/scatter-gather.md) / [Lifecycle](concepts/experiment-lifecycle.md)                                    |
| Guides               | [Defining Experiments](guides/defining-experiments.md) / [Running](guides/running-experiments.md) / [Workers](guides/workers.md) / [Results](guides/retrieving-results.md) |
| Deployment           | [Local](deployment/local.md) / [Cloud](deployment/cloud.md)                                                                                                                |
| Reference            | [Configuration](reference/configuration.md) / [API](reference/api.md)                                                                                                      |
| Example Repo         | [szvsw/scythe-example](https://github.com/szvsw/scythe-example)                                                                                                            |
| Self-hosting Hatchet | [szvsw/hatchet-sst](https://github.com/szvsw/hatchet-sst)                                                                                                                  |
| Blog                 | [Building Scythe](blog/building-scythe.md)                                                                                                                                 |
| PyPI                 | [scythe-engine](https://pypi.org/project/scythe-engine)                                                                                                                    |
