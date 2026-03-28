# Workflow & Single-Run Experiments

Scythe's core strength is running large batches of experiments via scatter/gather. But sometimes you need a **versioned one-off run** -- a single experiment execution that still benefits from Scythe's versioning, S3 layout, and metadata infrastructure. Single-spec allocation supports this for any runnable, whether it is a `Standalone` task or a multi-step Hatchet `Workflow`.

## Why Single-Spec Allocation?

When you pass a **single spec** (rather than a list) to `allocate()`, Scythe triggers the runnable directly on Hatchet, bypassing scatter/gather entirely. This is useful when you want to:

- **Run a versioned one-off** -- Execute a single simulation with full Scythe versioning and S3 metadata, without the overhead of scatter/gather.
- **Test or debug** -- Fire off a single run of a task that would normally be batched, to verify it works before scaling up.
- **Run a multi-step pipeline** -- Use a Hatchet `Workflow` with sequential or parallel steps, DAGs, or per-step retry/timeout configuration.
- **Track existing Hatchet workflows** -- Wrap an existing workflow with Scythe's versioning and experiment S3 layout.

Both `Standalone` and `Workflow` runnables support single-spec allocation, since both inherit from Hatchet's `BaseWorkflow`.

## Single-Spec Allocation with a Standalone

Any experiment registered with `@ExperimentRegistry.Register()` can be allocated with a single spec:

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

run, ref = experiment.allocate(
    spec,  # single spec, not a list
    version="bumpminor",
)
```

The same runnable can also be batch-allocated with a list of specs for scatter/gather execution -- single-spec allocation is just a convenient alternative when you only need one run.

## Multi-Step Workflows

For experiments that involve multiple sequential or parallel steps, you can define a Hatchet `Workflow` using the functional/decorator API:

```python title="workflows/my_pipeline.py"
from datetime import timedelta

from hatchet_sdk import Context
from pydantic import BaseModel, Field

from scythe.base import ExperimentInputSpec
from scythe.hatchet import hatchet


class PipelineInput(ExperimentInputSpec):
    """Input for the multi-step pipeline."""

    temperature: float = Field(..., description="Temperature [K]", ge=0)
    pressure: float = Field(..., description="Pressure [Pa]", ge=0)


class PreprocessOutput(BaseModel):
    adjusted_temperature: float


class SimulateOutput(BaseModel):
    result: float


my_pipeline = hatchet.workflow(name="my_pipeline", input_validator=PipelineInput)


@my_pipeline.task(execution_timeout=timedelta(seconds=30))
async def preprocess(input: PipelineInput, ctx: Context) -> PreprocessOutput:
    return PreprocessOutput(adjusted_temperature=input.temperature * 1.05)


@my_pipeline.task(parents=[preprocess], execution_timeout=timedelta(minutes=5))
async def simulate(input: PipelineInput, ctx: Context) -> SimulateOutput:
    prep = ctx.task_output(preprocess)
    # ... simulation logic using preprocessed data ...
    return SimulateOutput(result=prep.adjusted_temperature * input.pressure)


@my_pipeline.task(parents=[simulate], execution_timeout=timedelta(seconds=30))
async def postprocess(input: PipelineInput, ctx: Context) -> dict:
    sim = ctx.task_output(simulate)
    return {"final_result": sim.result}
```

Each task receives the workflow's input (a `PipelineInput` instance) and a Hatchet `Context`. Tasks declare dependencies via the `parents` parameter, and access parent outputs with `ctx.task_output()`. Independent tasks with no parent dependencies run in parallel automatically.

### Registering a Workflow

Use `ExperimentRegistry.Include()` to register the workflow with Scythe:

```python
from scythe.registry import ExperimentRegistry
from workflows.my_pipeline import my_pipeline

ExperimentRegistry.Include(my_pipeline)
```

This makes the workflow available for allocation via `BaseExperiment` and ensures workers can serve it.

!!! note
`Include()` accepts both `Standalone` and `Workflow` objects. For standalone tasks created by `@ExperimentRegistry.Register()`, registration happens automatically via the decorator.

### Allocating a Workflow

```python
from scythe.experiments import BaseExperiment
from workflows.my_pipeline import my_pipeline, PipelineInput

experiment = BaseExperiment(runnable=my_pipeline)

spec = PipelineInput(
    temperature=300.0,
    pressure=1e5,
    experiment_id="placeholder",
    sort_index=0,
)

run, ref = experiment.allocate(spec, version="bumpminor")
```

## Return Types

The return type of `allocate()` depends on how it is called:

| Allocation style   | Return type                            |
| ------------------ | -------------------------------------- |
| `Sequence[TInput]` | `tuple[ExperimentRun, TaskRunRef]`     |
| Single `TInput`    | `tuple[ExperimentRun, WorkflowRunRef]` |

Both `TaskRunRef` and `WorkflowRunRef` support `.result()` for blocking and `.aio_result()` for async:

```python
result = ref.result()
# or: result = await ref.aio_result()
```

## S3 Layout Differences

Single-spec experiment runs use the same S3 directory structure as batch experiments, with one addition:

```
<bucket_prefix>/<experiment_name>/<version>/<timestamp>/
├── manifest.yml
├── experiment_io_spec.yml
├── input_artifacts.yml
├── specs.pq
├── workflow_spec.yml          # <-- only for single-spec runs
├── artifacts/
└── ...
```

The `workflow_spec.yml` file contains the serialized input spec for the run.

## Worker Setup

Workers serving Workflow runnables should pass them via `additional_workflows`:

```python
from scythe.worker import ScytheWorkerConfig
from workflows.my_pipeline import my_pipeline

config = ScytheWorkerConfig()
config.start(additional_workflows=[my_pipeline])
```

Standalone runnables are served automatically when registered with `@ExperimentRegistry.Register()` -- no extra worker configuration is needed for single-spec Standalone runs.

## Limitations

- **No batching for Workflows** -- `Workflow` runnables do not currently support batch allocation. Passing a `Sequence` of specs to a `Workflow` runnable raises a `TypeError`. If you need to run a workflow across many specs, allocate each spec individually.
- **No output validator for Workflows** -- `Workflow` runnables do not expose an `output_validator_type`, so the output schema section of `experiment_io_spec.yml` will be `NoneType`.
- **No scatter/gather for single-spec runs** -- Result aggregation via the scatter/gather tree is not available for single-spec allocations. For Workflows, the workflow handles its own result logic.
