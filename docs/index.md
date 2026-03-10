# Scythe

Scythe is a lightweight tool which helps you seed and reap (scatter and gather)
embarrassingly parallel experiments via the asynchronous distributed queue [Hatchet](https://hatchet.run).

> The project is still in the VERY EARLY stages, and will likely evolve quite a bit in the
> second half of 2025.

- For a look into how a distributed computing stack comes together,
  check out the blog post: [Building Scythe](https://szvsw.github.io/scythe/blog/building-scythe)
- Example usage repository: [szvsw/scythe-example](https://github.com/szvsw/scythe-example)
- Self-hosting Hatchet: [szvsw/hatchet-sst](https://github.com/szvsw/hatchet-sst)

---

## Defining Experiments

Scythe experiments are defined using input and output schemas that inherit from `ExperimentInputSpec` and `ExperimentOutputSpec`:

```python
from pydantic import Field
from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.utils.filesys import FileReference

class SimInput(ExperimentInputSpec):
    r_value: float = Field(..., ge=0, le=15)
    weather_file: FileReference = Field(...)

class SimOutput(ExperimentOutputSpec):
    heating: float = Field(...)
    cooling: float = Field(...)
```

---

## Registering Experiments

### Standalone tasks (scatter/gather)

Decorate a function with `ExperimentRegistry.Register()` to automatically wrap it in a
Hatchet task and register it for scatter/gather execution:

```python
from scythe.registry import ExperimentRegistry

@ExperimentRegistry.Register(description="Run a building energy simulation")
def simulate_energy(input_spec: SimInput) -> SimOutput:
    """Run the simulation."""
    ...
    return SimOutput(heating=..., cooling=...)
```

The function can optionally accept a `tempdir: Path` argument for a task-scoped
temporary directory that is cleaned up automatically when the task finishes:

```python
from pathlib import Path

@ExperimentRegistry.Register()
def simulate_energy(input_spec: SimInput, tempdir: Path) -> SimOutput:
    output_path = tempdir / "results.pq"
    ...
    return SimOutput(..., timeseries=output_path)
```

### Hatchet Workflow support

In addition to simple standalone tasks, Scythe supports full Hatchet `Workflow` objects
(multi-step DAGs). Register an existing workflow with `ExperimentRegistry.Include()`:

```python
from hatchet_sdk.runnables.workflow import Workflow
from scythe.registry import ExperimentRegistry

my_workflow: Workflow[SimInput] = ...  # your Hatchet Workflow

ExperimentRegistry.Include(my_workflow)
```

`Include` accepts both `Standalone` and `Workflow` instances and stores them so they can
be looked up by name when deserialising a `BaseExperiment`.

---

## Running Experiments (Versioning)

Use `BaseExperiment` to version and launch an experiment run:

```python
from scythe.experiments import BaseExperiment

experiment = BaseExperiment(runnable=simulate_energy)

specs = [SimInput(experiment_id="placeholder", sort_index=i, r_value=3.0, ...) for i in range(100)]
run, ref = experiment.allocate(specs, version="bumpminor")
```

### Versioning strategies

The `version` argument of `allocate()` controls how the semantic version is advanced
relative to the most recent run found in the S3 bucket:

| Strategy | Behaviour |
|----------|-----------|
| `"bumpmajor"` (default) | Increment the major version, reset minor and patch to 0 |
| `"bumpminor"` | Increment the minor version, reset patch to 0 |
| `"bumppatch"` | Increment the patch version |
| `"keep"` | Reuse the current latest version (a new timestamped run is still created) |
| `SemVer(major=2, minor=0, patch=0)` | Pin an explicit version |

If no previous run exists in the bucket the version is initialised to `v1.0.0`.

### `SemVer`

```python
from scythe.experiments import SemVer

v = SemVer.FromString("v1.2.3")
print(v.next_minor_version())  # v1.3.0
print(v.next_major_version())  # v2.0.0
```

### S3 bucket layout

After a run completes the bucket will contain the following hierarchy:

```
<bucket_prefix>/
└── <experiment_name>/        # e.g. "scythe_experiment_simulate_energy"
    └── <version>/            # e.g. "v1.0.0"
        └── <datetime>/       # e.g. "2025-07-23_12-59-51"
            ├── manifest.yml
            ├── experiment_io_spec.yml
            ├── input_artifacts.yml
            ├── specs.pq
            ├── artifacts/
            │   └── <field>/
            │       └── <file>
            ├── final/
            │   ├── scalars.pq
            │   ├── result_file_refs.pq
            │   └── <user-dataframe>.pq
            └── results/
                └── <field>/
                    └── <workflow_run_id>.<ext>
```

For `Workflow`-backed experiments, an additional `workflow_spec.yml` is written alongside the manifest.

---

## Querying Results

```python
# All versions of an experiment
versions = experiment.list_versions()

# Latest version
latest = experiment.latest_version()

# Latest run results (dict of parquet stem → S3 key)
results = experiment.latest_results

# Results for a specific version
results_v1 = experiment.latest_results_for_version(SemVer(major=1))
```

---

## Worker Configuration

See the [Worker Configuration](worker-configuration.md) page for details on:

- `ScytheWorkerConfig` – slots, durable slots, and worker name
- `ScytheWorkerLabel` – routing experiments to workers with specific capabilities (`HAS_GPU`, `HIGH_MEMORY`, `HIGH_CPU`)
- `WorkerNameConfig` – automatic worker naming in AWS Batch / Copilot, Fly.io, and local environments
- Separating fan-out and leaf workers with `DOES_FAN` / `DOES_LEAF`
