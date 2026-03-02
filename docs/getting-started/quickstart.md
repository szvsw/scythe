# Quickstart

This guide walks through defining, running, and collecting results from an experiment using Scythe. The complete working code is available in the [scythe-example](https://github.com/szvsw/scythe-example) repository.

## 1. Define Input and Output Schemas

Scythe experiments are typed. You define your inputs and outputs as Pydantic models inheriting from `ExperimentInputSpec` and `ExperimentOutputSpec`:

```python title="experiments/building_energy.py"
from pathlib import Path
from typing import Literal

from pydantic import Field
from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.registry import ExperimentRegistry
from scythe.utils.filesys import FileReference


class BuildingSimulationInput(ExperimentInputSpec):
    """Simulation inputs for a building energy model."""

    r_value: float = Field(..., description="The R-Value of the building [m2K/W]", ge=0, le=15)
    lpd: float = Field(..., description="Lighting power density [W/m2]", ge=0, le=20)
    setpoint: float = Field(..., description="Thermostat setpoint [deg.C]", ge=12, le=30)
    economizer: Literal["NoEconomizer", "DifferentialDryBulb", "DifferentialEnthalpy"] = Field(
        ..., description="The type of economizer to use",
    )
    weather_file: FileReference = Field(..., description="Weather file [.epw]")  # (1)!
    design_day_file: FileReference = Field(..., description="Design day file [.ddy]")


class BuildingSimulationOutput(ExperimentOutputSpec):
    """Simulation outputs for a building energy model."""

    heating: float = Field(..., description="Annual heating energy usage, kWh/m2", ge=0)
    cooling: float = Field(..., description="Annual cooling energy usage, kWh/m2", ge=0)
    lighting: float = Field(..., description="Annual lighting energy usage, kWh/m2", ge=0)
    equipment: float = Field(..., description="Annual equipment energy usage, kWh/m2", ge=0)
    fans: float = Field(..., description="Annual fans energy usage, kWh/m2", ge=0)
    pumps: float = Field(..., description="Annual pumps energy usage, kWh/m2", ge=0)
    timeseries: FileReference = Field(..., description="Timeseries data")  # (2)!
```

1. `FileReference` accepts `S3Url | HttpUrl | pathlib.Path`. Local `Path` values are automatically uploaded to S3 during allocation.
2. Output `FileReference` fields of type `Path` are automatically uploaded to S3 when the task completes.

## 2. Register the Experiment

Decorate your simulation function with `@ExperimentRegistry.Register()`. The function receives the input spec and an optional `tempdir` for scratch files:

```python title="experiments/building_energy.py (continued)"
@ExperimentRegistry.Register()
def simulate_energy(
    input_spec: BuildingSimulationInput, tempdir: Path
) -> BuildingSimulationOutput:
    """Initialize and execute an energy model of a building."""

    # Your simulation logic here...
    pth = tempdir / "timeseries.csv"
    with open(pth, "w") as f:
        f.write("time,energy\n0,100\n1,200\n")

    return BuildingSimulationOutput(
        heating=0,
        cooling=0,
        lighting=0,
        equipment=0,
        fans=0,
        pumps=0,
        timeseries=pth,
    )
```

The decorator wraps your function in Hatchet task middleware that handles:

- Fetching remote artifacts referenced in the input spec to a local cache
- Creating and cleaning up a per-task temporary directory
- Uploading output `FileReference` fields to S3
- Extracting scalar results into a DataFrame
- Serializing any additional DataFrames to S3

## 3. Allocate the Experiment

Create a population of input specs and allocate an experiment run:

```python title="allocate.py"
import numpy as np
import pandas as pd
from scythe.experiments import BaseExperiment
from scythe.scatter_gather import RecursionMap

from experiments.building_energy import BuildingSimulationInput, simulate_energy


def sample(n: int = 10) -> list[BuildingSimulationInput]:
    df = pd.DataFrame({
        "r_value": np.random.uniform(0, 15, size=n),
        "lpd": np.random.uniform(0, 20, size=n),
        "setpoint": np.random.uniform(12, 30, size=n),
        "economizer": np.random.choice(
            ["NoEconomizer", "DifferentialDryBulb", "DifferentialEnthalpy"], size=n
        ),
        "weather_file": ["artifacts/weather.epw"] * n,
        "design_day_file": ["artifacts/design_day.ddy"] * n,
        "experiment_id": "placeholder",
        "sort_index": range(n),
    })
    return [
        BuildingSimulationInput.model_validate(row.to_dict())
        for _, row in df.iterrows()
    ]


specs = sample(10)

experiment = BaseExperiment(experiment=simulate_energy)

run, ref = experiment.allocate(
    specs,
    version="bumpminor",  # (1)!
    recursion_map=RecursionMap(factor=2, max_depth=2),  # (2)!
)
```

1. Auto-resolves the latest version in S3 and increments the minor version (e.g. `v1.2.0` becomes `v1.3.0`). Options: `bumpmajor`, `bumpminor`, `bumppatch`, `keep`.
2. Controls the scatter/gather tree shape. `factor=2` means each node fans out to 2 children; `max_depth=2` limits the recursion depth.

The `allocate` call:

- Validates all specs against the registered input type
- Uploads local file artifacts to S3
- Serializes specs to a Parquet file in S3
- Triggers the scatter/gather workflow on Hatchet
- Writes a `manifest.yml`, `experiment_io_spec.yml`, and `input_artifacts.yml` to S3

## 4. Start a Worker

Workers pick up tasks from Hatchet and execute them. The worker entry point imports all registered experiments and starts listening:

```python title="main.py"
from scythe.worker import ScytheWorkerConfig

from experiments import *  # noqa: F403

if __name__ == "__main__":
    worker_config = ScytheWorkerConfig()
    worker_config.start()
```

Run it with your environment variables:

```sh
uv run --env-file .env main.py
```

## 5. Collect Results

Once the experiment completes, the scatter/gather root writes aggregated Parquet files to the `final/` directory of your experiment run in S3:

- `scalars.pq` -- All scalar output fields, indexed by input specs
- `result_file_refs.pq` -- URIs of any `FileReference` output fields
- Any additional DataFrames you added to `ExperimentOutputSpec.dataframes`

You can also wait on the result programmatically:

```python
result = ref.result()  # blocking
# or: result = await ref.aio_result()  # async
```

## Next Steps

- Learn about the [architecture](../concepts/architecture.md) to understand how the pieces fit together
- Read the guide on [defining experiments](../guides/defining-experiments.md) for advanced schema patterns
- See [deployment options](../deployment/local.md) for running with Docker Compose
