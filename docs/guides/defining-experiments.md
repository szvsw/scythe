# Defining Experiments

This guide covers how to define experiment schemas and register simulation functions with Scythe.

## Input Specs

All experiment inputs inherit from `ExperimentInputSpec`, which itself inherits from `BaseSpec`:

```python
from pydantic import Field
from scythe.base import ExperimentInputSpec


class MyInput(ExperimentInputSpec):
    temperature: float = Field(..., description="Temperature [K]", ge=0)
    pressure: float = Field(..., description="Pressure [Pa]", ge=0)
    material: str = Field(..., description="Material identifier")
```

### Inherited Fields

`ExperimentInputSpec` provides several fields automatically:

| Field                  | Type                            | Description                                                  |
| ---------------------- | ------------------------------- | ------------------------------------------------------------ |
| `experiment_id`        | `str`                           | Fully resolved experiment identifier (set during allocation) |
| `sort_index`           | `int`                           | Position in the spec list (set during allocation)            |
| `workflow_run_id`      | `str \| None`                   | Hatchet workflow run ID (set at task execution time)         |
| `root_workflow_run_id` | `str \| None`                   | Root scatter/gather workflow run ID                          |
| `storage_settings`     | `ScytheStorageSettings \| None` | S3 bucket and prefix (injected by scatter/gather)            |

You do not need to set these when creating specs -- they are populated automatically during allocation and execution.

### Inherited Methods

- `log(msg)` -- Log a message. During task execution, this is redirected to the Hatchet context logger so messages appear in the Hatchet dashboard.
- `fetch_uri(uri, use_cache=True)` -- Fetch a file from S3, HTTP, or the local filesystem and return the local path. Results are cached by default.
- `make_multiindex(n_rows=1, additional_index_data=None)` -- Construct a `pd.MultiIndex` from the spec fields (plus any `computed_features`), used for indexing output DataFrames.

### Computed Features

Sometimes you need extra index levels that are **derived** from existing fields rather than stored as their own Pydantic fields. Override the `computed_features` property to return a dictionary of scalar values that will be merged into the `MultiIndex` automatically:

```python
from pydantic import Field
from scythe.base import ComputedFeatureValue, ExperimentInputSpec


class MyInput(ExperimentInputSpec):
    temperature: float = Field(..., description="Temperature [K]", ge=0)
    pressure: float = Field(..., description="Pressure [Pa]", ge=0)

    @property
    def computed_features(self) -> dict[str, ComputedFeatureValue]:
        return {"temp_bucket": "high" if self.temperature > 500 else "low"}
```

Computed feature keys must not overlap with Pydantic field names or any keys supplied via `additional_index_data`. Values must be `int`, `float`, or `str` (the `ComputedFeatureValue` type alias). In `make_multiindex`, computed features are inserted after the Pydantic field dump and before `additional_index_data`.

## Output Specs

Output schemas inherit from `ExperimentOutputSpec`:

```python
from scythe.base import ExperimentOutputSpec


class MyOutput(ExperimentOutputSpec):
    energy: float = Field(..., description="Total energy [J]", ge=0)
    efficiency: float = Field(..., description="Efficiency [%]", ge=0, le=100)
```

Scalar fields (anything that is not a `FileReference` or `dataframes`) are automatically collected into a `scalars.pq` DataFrame at the experiment level.

### The `dataframes` Field

`ExperimentOutputSpec` includes a built-in `dataframes: dict[str, pd.DataFrame]` field for returning additional DataFrames beyond the scalar outputs. This is useful for timeseries, per-timestep metrics, or any tabular data that varies in size across runs:

```python
import pandas as pd

results_df = pd.DataFrame({
    "timestep": range(8760),
    "temperature": temps,
    "load": loads,
})
results_df.index = input_spec.make_multiindex(n_rows=len(results_df))

return MyOutput(
    energy=total_energy,
    efficiency=eff,
    dataframes={"hourly": results_df},
)
```

Each DataFrame in `dataframes` is serialized to Parquet and uploaded to S3 individually per task. At the experiment level, all DataFrames with the same key are concatenated across tasks into a single Parquet file in the `final/` directory.

!!! note
The keys `scalars` and `result_file_refs` are reserved and will raise an error if used in `dataframes`.

## FileReference

`FileReference` is a union type that accepts file paths from multiple sources:

```python
from scythe.utils.filesys import FileReference

FileReference = S3Url | HttpUrl | Path | FilePath
```

### In Input Specs

When you include a `FileReference` field in your input spec:

- **Local `Path` values** are uploaded to S3 during allocation and rewritten as `S3Url` references. This ensures workers can access the files regardless of where they run.
- **`S3Url` and `HttpUrl` values** are passed through as-is.

During task execution, all remote file references are automatically fetched to a local cache before your function is called (unless you disable this with `auto_fetch_files=False`).

```python
class SimInput(ExperimentInputSpec):
    config_file: FileReference = Field(..., description="Simulation config")
    weather_data: FileReference = Field(..., description="Weather data file")
```

### In Output Specs

When you include a `FileReference` field in your output spec:

- **Local `Path` values** (typically files written to `tempdir`) are uploaded to S3 after your function returns. The field is rewritten with the S3 URI.
- All file reference URIs across tasks are collected into `result_file_refs.pq`.

```python
class SimOutput(ExperimentOutputSpec):
    report: FileReference = Field(..., description="PDF report")
    raw_data: FileReference = Field(..., description="Raw output data")
```

## Registering Experiments

Use `@ExperimentRegistry.Register()` to make your function a Scythe experiment:

```python
from scythe.registry import ExperimentRegistry


@ExperimentRegistry.Register()
def my_simulation(input_spec: MyInput) -> MyOutput:
    """Run a simulation."""
    ...
    return MyOutput(energy=42.0, efficiency=95.0)
```

### With a Temporary Directory

If your simulation needs scratch space for intermediate files, add a `tempdir: Path` parameter:

```python
from pathlib import Path


@ExperimentRegistry.Register()
def my_simulation(input_spec: MyInput, tempdir: Path) -> MyOutput:
    """Run a simulation that writes intermediate files."""
    output_file = tempdir / "results.csv"
    # ... write to output_file ...
    return MyOutput(
        energy=42.0,
        efficiency=95.0,
        report=output_file,  # automatically uploaded to S3
    )
```

The temporary directory is created before your function runs and cleaned up after results are extracted.

### Register Options

The `Register` decorator accepts several options:

| Parameter                | Default                       | Description                                                                               |
| ------------------------ | ----------------------------- | ----------------------------------------------------------------------------------------- |
| `retries`                | `1`                           | Number of retry attempts on failure                                                       |
| `schedule_timeout`       | `1h`                          | Maximum time to wait for a worker to pick up the task                                     |
| `execution_timeout`      | `1m`                          | Maximum time for the task to run                                                          |
| `name`                   | `scythe_experiment_<fn_name>` | Custom task name for Hatchet                                                              |
| `description`            | Function docstring            | Task description in Hatchet                                                               |
| `desired_worker_labels`  | `None`                        | Worker affinity labels for routing                                                        |
| `auto_fetch_files`       | `True`                        | Whether to automatically fetch remote files before calling your function                  |
| `local_file_location`    | `"cache"`                     | Where to store fetched files: `"cache"` (shared) or `"copied-to-tempdir"` (per-task copy) |
| `overwrite_log_method`   | `True`                        | Whether to redirect `input_spec.log()` to the Hatchet context logger                      |
| `inject_workflow_run_id` | `True`                        | Whether to set `workflow_run_id` on the input spec                                        |

### Production Example

Here is a more realistic registration with custom timeouts and retries:

```python
@ExperimentRegistry.Register(
    retries=2,
    schedule_timeout="10h",
    execution_timeout="30m",
)
def simulate_building(
    input_spec: BuildingSpec, tempdir: Path
) -> BuildingOutput:
    """Run a building energy simulation."""
    ...
```

## Registering Workflow Runnables

In addition to standalone functions, you can register Hatchet `Workflow` objects with `ExperimentRegistry.Include()`. This is useful for multi-step pipelines or complex DAGs:

```python
from scythe.registry import ExperimentRegistry

ExperimentRegistry.Include(my_workflow)
```

Workflow runnables are allocated with a single spec (not a batch) and bypass the scatter/gather system entirely. For a complete guide on defining and running workflows, as well as single-spec allocation for any runnable, see [Workflow & Single-Run Experiments](workflow-experiments.md).

## Multiple Experiments

You can define multiple experiments in your project. Each gets its own input/output types and registration. The worker will serve all registered experiments:

```python title="experiments/__init__.py"
from experiments.building_energy import *  # noqa: F403
from experiments.orbital_dynamics import *  # noqa: F403
from experiments.lifespan import *  # noqa: F403
```

```python title="main.py"
from scythe.worker import ScytheWorkerConfig
from experiments import *  # noqa: F403

if __name__ == "__main__":
    ScytheWorkerConfig().start()
```

Each experiment allocates independently and writes to its own S3 directory based on the function name.
