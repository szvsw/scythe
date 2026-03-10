# Worker Configuration

Scythe provides a `ScytheWorkerConfig` settings class that simplifies starting a worker with the right capabilities and label configuration.

## Quick Start

```python
from scythe.worker import ScytheWorkerConfig

config = ScytheWorkerConfig()
config.start()
```

All settings can be supplied as environment variables (prefixed with `SCYTHE_WORKER_`) or passed directly when constructing the config object.

---

## `ScytheWorkerConfig`

`ScytheWorkerConfig` inherits from `pydantic_settings.BaseSettings` (env prefix: `SCYTHE_WORKER_`).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `NAME` | `str \| None` | `None` | Override the auto-generated worker name. |
| `SLOTS` | `int \| None` | `None` | Number of concurrent task slots. Defaults to `cpu_count - 1` (or `cpu_count` when `cpu_count < 8`). |
| `DURABLE_SLOTS` | `int \| None` | `None` | Number of durable slots. Defaults to `1000`. |
| `HIGH_MEMORY` | `bool` | `False` | Advertise this worker as having high memory. |
| `HIGH_CPU` | `bool` | `False` | Advertise this worker as having high CPU. |
| `HAS_GPU` | `bool` | `False` | Advertise this worker as having a GPU. |
| `DOES_FAN` | `bool` | `True` | Register the scatter/gather fan-out workflow on this worker. |
| `DOES_LEAF` | `bool` | `True` | Register the individual experiment tasks on this worker. |

### `start()`

```python
config.start(
    experiments=[my_experiment_fn],       # optional: register additional experiment functions
    additional_workflows=[my_workflow],   # optional: register additional Hatchet workflows
)
```

* `experiments` – a list of bare experiment functions that have **not** yet been registered with `ExperimentRegistry`. Scythe will call `ExperimentRegistry.Register()` on each one before starting the worker.
* `additional_workflows` – any extra Hatchet `BaseWorkflow` objects to register on the worker alongside the Scythe-managed ones.

---

## `ScytheWorkerLabel`

Use `ScytheWorkerLabel` to declare that a specific experiment requires a particular type of worker. Tasks decorated with `desired_worker_labels` will only be dispatched to workers that advertise the matching label.

```python
from scythe.worker import ScytheWorkerLabel
from scythe.registry import ExperimentRegistry

@ExperimentRegistry.Register(
    desired_worker_labels=ScytheWorkerLabel.HAS_GPU.worker_label
)
def my_gpu_experiment(input_spec: MyInput) -> MyOutput:
    ...
```

Multiple labels can be combined:

```python
@ExperimentRegistry.Register(
    desired_worker_labels={
        **ScytheWorkerLabel.HAS_GPU.worker_label,
        **ScytheWorkerLabel.HIGH_MEMORY.worker_label,
    }
)
def my_experiment(input_spec: MyInput) -> MyOutput:
    ...
```

Available labels:

| Label | `StrEnum` value |
|-------|----------------|
| `ScytheWorkerLabel.HIGH_MEMORY` | `"high_memory"` |
| `ScytheWorkerLabel.HIGH_CPU` | `"high_cpu"` |
| `ScytheWorkerLabel.HAS_GPU` | `"has_gpu"` |

The corresponding environment variables to advertise these on a worker are:

```
SCYTHE_WORKER_HIGH_MEMORY=true
SCYTHE_WORKER_HIGH_CPU=true
SCYTHE_WORKER_HAS_GPU=true
```

---

## Worker Naming (`WorkerNameConfig`)

By default, the worker name is automatically derived from its hosting environment:

| Environment | Example Name |
|-------------|--------------|
| Local | `ScytheWorker--Local` |
| Fly.io (`FLY_REGION` env var set) | `ScytheWorker--FlyIAD` |
| AWS Batch (`AWS_BATCH_JOB_ARRAY_INDEX` set) | `ScytheWorker--AWSBatch0003` |
| AWS Copilot (`COPILOT_ENVIRONMENT_NAME` set) | `ScytheWorker--AWSCopilotPROD` |

Override the name entirely via `SCYTHE_WORKER_NAME`:

```
SCYTHE_WORKER_NAME=my-custom-worker
```

---

## Separating Fan-out and Leaf Workers

In large-scale deployments it can be useful to run the scatter/gather orchestration on a dedicated worker separate from the workers that execute the actual experiment tasks. Use `DOES_FAN` and `DOES_LEAF` to control which workflows each worker registers:

```python
# Orchestration-only worker (handles scatter/gather, no experiment tasks)
fan_config = ScytheWorkerConfig(DOES_FAN=True, DOES_LEAF=False)
fan_config.start()

# Leaf-only worker (executes experiment tasks, skips scatter/gather)
leaf_config = ScytheWorkerConfig(DOES_FAN=False, DOES_LEAF=True, HAS_GPU=True)
leaf_config.start()
```

Or via environment variables:

```
SCYTHE_WORKER_DOES_FAN=false
SCYTHE_WORKER_DOES_LEAF=true
SCYTHE_WORKER_HAS_GPU=true
```
