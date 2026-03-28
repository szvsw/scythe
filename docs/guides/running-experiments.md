# Running Experiments

This guide covers how to allocate and launch experiment runs using Scythe.

## Creating a BaseExperiment

The `BaseExperiment` class is the entry point for allocating experiment runs:

```python
from scythe.experiments import BaseExperiment
from my_experiments import simulate_energy

experiment = BaseExperiment(
    runnable=simulate_energy,  # (1)!
    run_name="custom_name",    # (2)!
)
```

1. The registered runnable -- either a `Standalone` experiment function or a Hatchet `Workflow` (or its Hatchet task name as a string).
2. Optional custom name for the S3 directory. Defaults to the Hatchet task name.

## Generating Specs

Before allocating, generate a list of input spec instances. You can use any sampling strategy:

```python
import numpy as np
import pandas as pd

from my_experiments import MyInput


def sample(n: int = 100) -> list[MyInput]:
    df = pd.DataFrame({
        "temperature": np.random.uniform(200, 400, size=n),
        "pressure": np.random.uniform(1e5, 1e7, size=n),
        "material": np.random.choice(["steel", "aluminum", "copper"], size=n),
        "experiment_id": "placeholder",
        "sort_index": range(n),
    })
    return [MyInput.model_validate(row.to_dict()) for _, row in df.iterrows()]
```

The `experiment_id` and `sort_index` fields will be overwritten during allocation, so placeholder values are fine.

## Allocating

Call `allocate()` to launch the experiment:

```python
from scythe.scatter_gather import RecursionMap

specs = sample(1000)

run, ref = experiment.allocate(
    specs,
    version="bumpminor",
    recursion_map=RecursionMap(factor=10, max_depth=1),
)
```

### What Happens During Allocation

1. The version is resolved against existing versions in S3
2. All specs are validated against the registered input type
3. `experiment_id` and `sort_index` are set on each spec
4. Local `FileReference` files are uploaded to S3
5. Specs are serialized to `specs.pq` in S3
6. Execution is triggered:
   - **Batch (list of specs)**: The scatter/gather workflow is triggered on Hatchet
   - **Single spec (one-off run)**: The runnable is triggered directly, bypassing scatter/gather. A `workflow_spec.yml` is also uploaded. Works with both `Standalone` and `Workflow` runnables.
7. Metadata files (`manifest.yml`, `experiment_io_spec.yml`, `input_artifacts.yml`) are written to S3

### Return Values

`allocate()` returns a tuple of `(ExperimentRun, ref)`:

- **`run`** (`ExperimentRun`) -- Metadata about the experiment run (version, timestamp, S3 keys).
- **`ref`** -- A Hatchet reference you can use to wait for completion. The type depends on the allocation:
  - `TaskRunRef` for batch scatter/gather runs
  - `WorkflowRunRef` for single-spec one-off runs

## Versioning

Scythe uses semantic versioning to organize experiment runs. Each allocation specifies a versioning strategy:

| Strategy      | Behavior                                       | Example              |
| ------------- | ---------------------------------------------- | -------------------- |
| `"bumpmajor"` | Increment major version, reset minor and patch | `v1.2.3` -> `v2.0.0` |
| `"bumpminor"` | Increment minor version, reset patch           | `v1.2.3` -> `v1.3.0` |
| `"bumppatch"` | Increment patch version                        | `v1.2.3` -> `v1.2.4` |
| `"keep"`      | Keep the current version                       | `v1.2.3` -> `v1.2.3` |

If no previous version exists in S3, the version starts at `v1.0.0` regardless of strategy.

Even with `"keep"`, each run is scoped by its timestamp, so you can have multiple runs for the same version:

```
simulate_energy/
├── v1.0.0/
│   ├── 2025-07-23_12-59-51/
│   └── 2025-07-23_14-30-00/
├── v1.1.0/
│   └── 2025-07-24_09-00-00/
```

You can also pass an explicit `SemVer` object:

```python
from scythe.experiments import SemVer

run, ref = experiment.allocate(
    specs,
    version=SemVer(major=2, minor=0, patch=0),
)
```

## Scatter/Gather Configuration

The `recursion_map` parameter controls how specs are distributed across the scatter/gather tree:

```python
from scythe.scatter_gather import RecursionMap

# No recursion -- root runs all tasks directly
run, ref = experiment.allocate(specs, version="bumpminor")

# Single level of fan-out with factor 10
run, ref = experiment.allocate(
    specs,
    version="bumpminor",
    recursion_map=RecursionMap(factor=10, max_depth=1),
)

# Two levels of recursion for very large experiments
run, ref = experiment.allocate(
    specs,
    version="bumpminor",
    recursion_map=RecursionMap(factor=10, max_depth=2),
)
```

When `recursion_map` is not specified, the default is `RecursionMap(factor=10, max_depth=0)` (no recursion).

For dynamic sizing based on payload, you can compute the recursion map programmatically:

```python
import math

n_specs = len(specs)
max_per_leaf = 100
factor = min(10, n_specs)
max_depth = max(0, math.ceil(math.log(n_specs / max_per_leaf, factor))) if n_specs > max_per_leaf else 0

recursion_map = RecursionMap(factor=factor, max_depth=max_depth)
```

## Single-Spec Allocation

You can pass a **single spec** (rather than a list) to `allocate()` for a versioned one-off run. This works with any runnable -- `Standalone` or `Workflow` -- and bypasses scatter/gather entirely:

```python
from scythe.experiments import BaseExperiment
from my_experiments import simulate_energy, MyInput

experiment = BaseExperiment(runnable=simulate_energy)

spec = MyInput(
    temperature=300.0,
    pressure=1e5,
    material="steel",
    experiment_id="placeholder",
    sort_index=0,
)

run, ref = experiment.allocate(spec, version="bumpminor")
```

The runnable is triggered directly on Hatchet, giving you full Scythe versioning and S3 metadata for a single run. This is useful for testing, debugging, or one-off experiments. For more details, including multi-step `Workflow` pipelines, see [Workflow & Single-Run Experiments](workflow-experiments.md).

## Waiting for Results

The `ref` returned by `allocate()` lets you wait for the experiment to complete:

```python
# Blocking
result = ref.result()

# Async
result = await ref.aio_result()
```

For batch allocations, the result is a `ScatterGatherResult` containing the S3 URIs of the aggregated output DataFrames. For single-spec allocations, the result is the runnable's return value.

## S3 Directory Layout

After a successful run, the experiment directory in S3 contains:

```
<bucket_prefix>/<experiment_name>/<version>/<timestamp>/
├── manifest.yml                    # Run metadata
├── experiment_io_spec.yml          # JSON Schema for input/output types
├── input_artifacts.yml             # S3 URIs of uploaded input artifacts
├── specs.pq                        # All input specs as Parquet
├── workflow_spec.yml               # Input spec (single-spec runs only)
├── artifacts/                      # Uploaded input artifact files
│   └── <field_name>/
│       └── <file>
├── scatter-gather/                 # Intermediate scatter/gather data (batch only)
│   ├── input/
│   └── output/
├── final/                          # Aggregated results (batch only)
│   ├── scalars.pq
│   ├── result_file_refs.pq
│   └── <user_dataframe>.pq
└── results/                        # Per-task output files
    └── <field_name>/
        └── <run_id>.<ext>
```
