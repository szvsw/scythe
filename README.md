# Scythe

[![Release](https://img.shields.io/github/v/release/szvsw/scythe)](https://img.shields.io/github/v/release/szvsw/scythe)
[![Build status](https://img.shields.io/github/actions/workflow/status/szvsw/scythe/main.yml?branch=main)](https://github.com/szvsw/scythe/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/szvsw/scythe/branch/main/graph/badge.svg)](https://codecov.io/gh/szvsw/scythe)
[![Commit activity](https://img.shields.io/github/commit-activity/m/szvsw/scythe)](https://img.shields.io/github/commit-activity/m/szvsw/scythe)
[![License](https://img.shields.io/github/license/szvsw/scythe)](https://img.shields.io/github/license/szvsw/scythe)

Scythe is a lightweight tool which helps you seed and reap (scatter and gather)
embarrassingly parallel experiments via the asynchronous distributed queue [Hatchet](https://hatchet.run).

> The project is still in the VERY EARLY stages, and will likely evolve quite a bit in the
> second half of 2025.

- **Github repository**: <https://github.com/szvsw/scythe/>
- **Documentation** <https://szvsw.github.io/scythe/>
- **Example usage repository**: <https://github.com/szvsw/scythe-example>
- **Self-hosting Hatchet**: <https://github.com/szvsw/hatchet-sst>

## Motivation

In my experience helping colleagues with their research projects,
academic researchers and engineers often have the ability to define their
experiments via input and output specs fairly well and would love to run at large scales,
but often get limited by a lack of experience with distributed computing techniques,
eg. artifact infil- and exfiltration, handling errors, interacting with supercomputing schedulers,
dealing with cloud infrastructure, etc.

The goal of Scythe is to abstract away some of these
details to let researchers focus on what they are familiar with (i.e. writing consistent
input and output schemas and the computation logic that transforms data from inputs into
outputs) while automating the boring but necessary work to run millions of simulations (e.g.
serializing data to and from cloud buckets, configuring queues, etc).

There are of course lots of data engineering orchestration tools out there already, but this
is a bit more lightweight and hopefully a little simpler to use, at the expense of fewer bells and whistles (for now)
like robust dataset lineage, etc.

[Hatchet](https://hatchet.run) is already very easy (and fun!) to use for newcomers to
distributed computing, so I recommend checking out their docs - you might be better off
simply directly running Hatchet! Scythe is just a lightweight modular layer on top of it
which is really tailored to the use case of generating large datasets of consistently structured
experiment inputs and outputs. Another option you might check out would be something like [Coiled + Dask](https://coiled.io/).

## Installation

With [uv](https://astral.sh/uv):

`uv add scythe-engine`

With [poetry](https://python-poetry.org):

`uv add scythe-engine`

With pip:

`pip install scythe-engine`

## Documentation

Coming soon...

However, in the meantime, check out the [example project](https://github.com/szvsw/scythe-example) to get an idea of what using Scythe with Hatchet looks like.

### Example

Scythe is useful for running many parallel simulations with a common I/O interface. It abstracts away the logic of uploading and referencing artifacts, issuing simulations and combining results into well-structured dataframes and parquet files.

After an experiment is finished, you will have a directory in your S3 bucket
with the following structure:

```
<experiment_id>/
├──── <datetime>/
│     ├──── manifest.yml
│     ├──── experiment_io_spec.yml
│     ├──── input_artifacts.yml
│     ├──── specs.pq
│     ├──── artifacts/
│     │     ├──── <field-1>/
│     │     │     ├──── file1.ext
│     │     │     └──── file2.ext
│     │     └──── <field-1>/
│     │     │     ├──── file1.ext
│     │     │     └──── file2.ext
│     │     ...
│     ├──── scatter-gather/
│     │     ├──── input/
│     │     └──── output/
│     ├──── final/
│     │     ├──── scalars.pq
│     │     ├──── <user-dataframe>.pq
│     │     ├──── <user-dataframe>.pq
├──── <datetime>/
...
```

In this example, we will demonstrate setting up a building energy simulation so we can create a dataset of energy modeling results for use in training a surrogate model.

To begin, we start by defining the schema of the inputs and outputs. The inputs will ultimately be converted into dataframes (where the defined input fields are columns). Similarly, the output schema fields will be used as columns of results dataframes (and the input dataframe will actualy be used as a MultiIndex). Note that `FileReference` inputs, which can be `HttpUrl | S3Url | Path`, which are of type `Path` will automatically be uploaded to S3 and re-referenced as S3 URIs.

```py
from pydantic import Field
from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.types import FileReference

class BuildingSimulationInput(ExperimentInputSpec):
    """Simulation inputs for a building energy model."""

    r_value: float = Field(default=..., description="The R-Value of the building [m2K/W]", ge=0, le=15)
    lpd: float = Field(default=..., description="Lighting power density [W/m2]", ge=0, le=20)
    setpoint: float = Field(default=..., description="Thermostat setpoint [deg.C]", ge=12, le=30)
    economizer: Literal["NoEconomizer", "DifferentialDryBulb", "DifferentialEnthalpy"] = Field(default=..., description="The type of economizer to use")
    weather_file: FileReference = Field(default=..., description="Weather file [.epw]")
    design_day_file: FileReference = Field(default=..., description="Weather file [.ddy]")


class BuildingSimulationOutput(ExperimentOutputSpec):
    """Simulation outputs for a building energy model."""

    heating: float = Field(default=..., description="Annual heating energy usage, kWh/m2", ge=0)
    cooling: float = Field(default=..., description="Annual cooling energy usage, kWh/m2", ge=0)
    lighting: float = Field(default=..., description="Annual lighting energy usage, kWh/m2", ge=0)
    equipment: float = Field(default=..., description="Annual equipment energy usage, kWh/m2", ge=0)
    fans: float = Field(default=..., description="Annual fans energy usage, kWh/m2", ge=0)
    pumps: float = Field(default=..., description="Annual pumps energy usage, kWh/m2", ge=0)
```

The schemas above will be exported into your results bucket as `experiment_io_spec.yaml` including any docstrings and descriptions.

_nb: you can also add your own dataframes to the outputs, e.g. for non-scalar values like timeseries and so on. documentation coming soon._

Next, we define the actual simulation logic. We will decorate the simulation function with an indicator that it should be a part of our `ExperimentRegistry`, which configures all of the fancy scatter/gather logic. Note that the function can only take a single argument (the schema defined previously) and can only return a single output instance of the previously defined output schema (though additional dataframes can be stored in the `dataframes` field inherited from the base `ExperimentOutputSpec`.).

```py
from scythe.registry import ExperimentRegistry

@ExperimentRegistry.Register()
def simulate_energy(input_spec: BuildingSimulationInput) -> BuildingSimulationOutput:
    """Initialize and execute an energy model of a building."""

    # do some work!
    ...

    return BuildingSimulationOutput(
        heating=...,
        cooling=...,
        lighting=...,
        equipment=...,
        fans=...,
        pumps=...
        dataframes=...,
    )
```

Since `BuildingSimulationInput` inherited from `ExperimentInputSpec`, some methods automatically exist on the class, e.g. `log` for writing messages to the worker logs, or methods for fetching common artifact files from remote resources like S3 or a web request into a cacheable filesystem.

**_TODO: document artifact fetching, writing artifacts per experiment_**

**_TODO: document allocating experiments, infra_**

After the experiment is finished running all tasks, it will automatically produce an output file `scalars.pq` with all of the results defined on your output schema for each of the individual simulations that were executed.

The index of the dataframe will itself be a dataframe with the input specs and some additional metadata, e.g:

`MultiIndex`
| experiment_id | sort_index | root_workflow_run_id | r_value | lpd | setpoint |
| --- | --- | --- | ---: |---:|---:|
| bem/v1 | 0 | abcd-efgh | 5.2 | 2.7 | 23.5 |
| bem/v1 | 1 | abcd-efgh | 2.9 | 1.3 | 19.7 |
| bem/v1 | 2 | abcd-efgh | 4.2 | 5.4 | 21.4 |

`Data`
| heating | cooling | lighting | equipment | fans | pumps |
| ---:| ---:| ---:| ---:| ---:| ---:|
| 17.2 | 15.3 | 10.1 | 13.8 | 14.2 | 1.4 |
| 21.7 | 5.4 | 9.2 | 5.8 | 10.3 | 2.0 |
| 19.5 | 8.9 | 12.5 | 13.7 | 8.9 | 0.9 |

**_TODO: document how additional dataframes of results are handled._**

Additionally, in your bucket, you will find a `manifest.yml` file as well as an `input_artifacts.yml` and `experiment_io_spec.yml`.

`manifest.yml`

```yaml
experiment_id: building_energy/v1/2025-07-23_12-59-51
experiment_name: scythe_experiment_simulate_energy
input_artifacts: s3://mit-sdl/scythe/building_energy/v1/2025-07-23_12-59-51/input_artifacts.yml
io_spec: s3://mit-sdl/scythe/building_energy/v1/2025-07-23_12-59-51/experiment_io_spec.yml
specs_uri: s3://mit-sdl/scythe/building_energy/v1/2025-07-23_12-59-51/specs.pq
workflow_run_id: f764ef33-a377-4572-a398-a2dc56a0810f
```

`input_artifacts.yml`

```yaml
files:
  design_day_file:
    - s3://mit-sdl/scythe/building_energy/v1/2025-07-23_12-59-51/artifacts/design_day_file/USA_MA_Boston.Logan_TMYx.ddy
    - s3://mit-sdl/scythe/building_energy/v1/2025-07-23_12-59-51/artifacts/design_day_file/USA_CA_Los.Angeles.LAX_TMYx.ddy
  weather_file:
    - s3://mit-sdl/scythe/building_energy/v1/2025-07-23_12-59-51/artifacts/weather_file/USA_MA_Boston.Logan_TMYx.epw
    - s3://mit-sdl/scythe/building_energy/v1/2025-07-23_12-59-51/artifacts/weather_file/USA_CA_Los.Angeles.LAX_TMYx.epw
```

`experiment_io_spec.yml`

```yaml
$defs:
  BuildingSimulationInput:
    additionalProperties: true
    description: Simulation inputs for a building energy model.
    properties:
      design_day_file:
        anyOf:
          - format: uri
            minLength: 1
            type: string
          - format: uri
            maxLength: 2083
            minLength: 1
            type: string
          - format: path
            type: string
          - format: file-path
            type: string
        description: Weather file [.ddy]
        title: Design Day File
      economizer:
        description: The type of economizer to use
        enum:
          - NoEconomizer
          - DifferentialDryBulb
          - DifferentialEnthalpy
        title: Economizer
        type: string
      experiment_id:
        description: The experiment_id of the spec
        title: Experiment Id
        type: string
      lpd:
        description: Lighting power density [W/m2]
        maximum: 20
        minimum: 0
        title: Lpd
        type: number
      r_value:
        description: The R-Value of the building [m2K/W]
        maximum: 15
        minimum: 0
        title: R Value
        type: number
      root_workflow_run_id:
        anyOf:
          - type: string
          - type: "null"
        default: null
        description: The root workflow run id of the leaf.
        title: Root Workflow Run Id
      setpoint:
        description: Thermostat setpoint [deg.C]
        maximum: 30
        minimum: 12
        title: Setpoint
        type: number
      sort_index:
        description: The sort index of the leaf.
        minimum: 0
        title: Sort Index
        type: integer
      weather_file:
        anyOf:
          - format: uri
            minLength: 1
            type: string
          - format: uri
            maxLength: 2083
            minLength: 1
            type: string
          - format: path
            type: string
          - format: file-path
            type: string
        description: Weather file [.epw]
        title: Weather File
      workflow_run_id:
        anyOf:
          - type: string
          - type: "null"
        default: null
        description: The workflow run id of the leaf.
        title: Workflow Run Id
    required:
      - experiment_id
      - sort_index
      - r_value
      - lpd
      - setpoint
      - economizer
      - weather_file
      - design_day_file
    title: BuildingSimulationInput
    type: object
  BuildingSimulationOutput:
    description: Simulation outputs for a building energy model.
    properties:
      cooling:
        description: Annual cooling energy usage, kWh/m2
        minimum: 0
        title: Cooling
        type: number
      equipment:
        description: Annual equipment energy usage, kWh/m2
        minimum: 0
        title: Equipment
        type: number
      fans:
        description: Annual fans energy usage, kWh/m2
        minimum: 0
        title: Fans
        type: number
      heating:
        description: Annual heating energy usage, kWh/m2
        minimum: 0
        title: Heating
        type: number
      lighting:
        description: Annual lighting energy usage, kWh/m2
        minimum: 0
        title: Lighting
        type: number
      pumps:
        description: Annual pumps energy usage, kWh/m2
        minimum: 0
        title: Pumps
        type: number
    required:
      - heating
      - cooling
      - lighting
      - equipment
      - fans
      - pumps
    title: BuildingSimulationOutput
    type: object
description: The input and output schema for the experiment.
properties:
  input:
    $ref: "#/$defs/BuildingSimulationInput"
    description: The input for the experiment.
  output:
    $ref: "#/$defs/BuildingSimulationOutput"
    description: The output for the experiment.
required:
  - input
  - output
title: ExperimentIO
type: object
```

## To-dos (help wanted!)

- Start documenting
- ExperimentRun class
- add method for writing dataframes or other artifact step outputs unique to task run to bucket
- Results downloaders
- automatic s3/https conversion to local in middleware
- optional handling of s3/https uris similarly to local on allocation (i.e. copying into experiment dir)
- consider an abc or protocol on input with a `run` method.
