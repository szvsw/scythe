# Workers

Workers are the processes that pick up and execute experiment tasks from Hatchet. Scythe provides `ScytheWorkerConfig` to configure and start workers with appropriate settings.

## Basic Worker Setup

A minimal worker imports all registered experiments and starts:

```python title="main.py"
from scythe.worker import ScytheWorkerConfig

from experiments import *  # noqa: F403

if __name__ == "__main__":
    worker_config = ScytheWorkerConfig()
    worker_config.start()
```

The `from experiments import *` line is essential -- it triggers the `@ExperimentRegistry.Register()` decorators, which register the experiments with the global registry. The worker then registers all known experiments (and the scatter/gather workflow) with Hatchet.

## Worker Roles

Scythe has two types of work: **fan** (scatter/gather orchestration) and **leaf** (actual experiment execution). By default, a worker handles both, but in production you typically want to separate them:

### Leaf Workers

Leaf workers run the actual simulation tasks. They tend to need more memory and CPU for the computation:

```sh
SCYTHE_WORKER_DOES_LEAF=True
SCYTHE_WORKER_DOES_FAN=False
SCYTHE_WORKER_SLOTS=1
```

Setting `SLOTS=1` means each worker runs one simulation at a time. This is appropriate when each simulation is CPU- or memory-intensive.

### Fan Workers

Fan workers handle the scatter/gather orchestration -- splitting specs, dispatching children, and aggregating results. They are I/O-bound rather than compute-bound:

```sh
SCYTHE_WORKER_DOES_LEAF=False
SCYTHE_WORKER_DOES_FAN=True
SCYTHE_WORKER_SLOTS=4
```

Fan workers can handle multiple concurrent scatter/gather operations since the work is primarily network I/O (reading/writing Parquet files to S3).

### Combined Workers

For development or small-scale runs, a single worker can handle both roles:

```sh
SCYTHE_WORKER_DOES_LEAF=True
SCYTHE_WORKER_DOES_FAN=True
```

## Configuration

`ScytheWorkerConfig` reads from environment variables with the `SCYTHE_WORKER_` prefix:

| Variable                      | Type   | Default        | Description                                      |
| ----------------------------- | ------ | -------------- | ------------------------------------------------ |
| `SCYTHE_WORKER_NAME`          | `str`  | Auto-generated | Custom worker name                               |
| `SCYTHE_WORKER_SLOTS`         | `int`  | CPU count      | Number of concurrent task slots                  |
| `SCYTHE_WORKER_DURABLE_SLOTS` | `int`  | `1000`         | Number of durable (persistent) task slots        |
| `SCYTHE_WORKER_HIGH_MEMORY`   | `bool` | `False`        | Label this worker as high-memory                 |
| `SCYTHE_WORKER_HIGH_CPU`      | `bool` | `False`        | Label this worker as high-CPU                    |
| `SCYTHE_WORKER_HAS_GPU`       | `bool` | `False`        | Label this worker as having a GPU                |
| `SCYTHE_WORKER_DOES_FAN`      | `bool` | `True`         | Whether this worker handles scatter/gather tasks |
| `SCYTHE_WORKER_DOES_LEAF`     | `bool` | `True`         | Whether this worker handles experiment tasks     |

### Slot Calculation

If `SCYTHE_WORKER_SLOTS` is not set, Scythe auto-detects the CPU count:

- For machines with fewer than 8 CPUs: `slots = cpu_count`
- For machines with 8+ CPUs: `slots = cpu_count - 1`

### Worker Labels

The `HIGH_MEMORY`, `HIGH_CPU`, and `HAS_GPU` flags are exposed as Hatchet worker labels. Scythe provides the `ScytheWorkerLabel` enum for type-safe label specification when routing experiments to appropriate workers:

```python
from scythe.worker import ScytheWorkerLabel

@ExperimentRegistry.Register(
    desired_worker_labels=ScytheWorkerLabel.HAS_GPU.worker_label,
)
def gpu_simulation(input_spec: MyInput) -> MyOutput:
    ...
```

You can combine multiple labels using dict unpacking:

```python
@ExperimentRegistry.Register(
    desired_worker_labels={
        **ScytheWorkerLabel.HAS_GPU.worker_label,
        **ScytheWorkerLabel.HIGH_MEMORY.worker_label,
    },
)
def heavy_gpu_simulation(input_spec: MyInput) -> MyOutput:
    ...
```

The available labels are:

| Label                           | Description            |
| ------------------------------- | ---------------------- |
| `ScytheWorkerLabel.HIGH_MEMORY` | Worker has high memory |
| `ScytheWorkerLabel.HIGH_CPU`    | Worker has high CPU    |
| `ScytheWorkerLabel.HAS_GPU`     | Worker has a GPU       |

## Worker Naming

Workers are automatically named based on their hosting environment:

| Environment | Name Pattern                   |
| ----------- | ------------------------------ |
| Local       | `ScytheWorker--Local`          |
| AWS Batch   | `ScytheWorker--AWSBatch0001`   |
| AWS Copilot | `ScytheWorker--AWSCopilotPROD` |
| Fly.io      | `ScytheWorker--FlyIAD`         |

This helps identify workers in the Hatchet dashboard when running multiple workers across environments.

## Running Workers

### With uv

```sh
uv run --env-file .env main.py
```

### With Docker

```dockerfile title="Dockerfile.worker"
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm AS main
COPY --from=ghcr.io/astral-sh/uv:0.6.16 /uv /uvx /bin/

WORKDIR /code
COPY uv.lock pyproject.toml README.md /code/
RUN uv sync --locked --no-install-project

COPY experiments /code/experiments/
COPY main.py /code/main.py
RUN uv sync --locked

CMD [ "uv", "run", "main.py" ]
```

### Dynamic Registration

You can also register experiments at worker start time instead of at import time:

```python
from scythe.worker import ScytheWorkerConfig
from my_experiments import my_simulation_fn

config = ScytheWorkerConfig()
config.start(experiments=[my_simulation_fn])
```

This calls `ExperimentRegistry.Register()` on each function before starting the worker.

### Additional Workflows

If you have Hatchet `Workflow` objects (e.g. multi-step pipelines registered via `ExperimentRegistry.Include()`) that the worker should serve, pass them with `additional_workflows`:

```python
from scythe.worker import ScytheWorkerConfig
from my_workflows import my_pipeline_workflow

config = ScytheWorkerConfig()
config.start(additional_workflows=[my_pipeline_workflow])
```

These workflows are registered with the Hatchet worker alongside the scatter/gather and leaf experiment workflows.
