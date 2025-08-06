# Building a toolkit for embarrassingly parallel experiments using Hatchet + SST.dev

In my experience helping colleagues with their research projects,
academic researchers and engineers (as in actual engineers, not SWEs) often have the ability to define their
experiments via input and output specs fairly well and would love to run at large scales,
but often get limited by a lack of experience with distributed computing techniques,
eg. artifact infil- and exfiltration, handling errors, interacting with supercomputing schedulers,
dealing with cloud infrastructure, etc.

As part of the collaborative research process, I ended up developing - and re-developing -
my workflows for running both my own and my colleagues' embarrassingly parallel experiments,
which eventually resulted in the creation of a library I've called [Scythe](https://github.com/szvsw/scythe).
Scythe is a lightweight tool which helps you seed and reap (scatter and gather)
embarrassingly parallel experiments via the asynchronous distributed queue [Hatchet](https://hatchet.run).

The goal of Scythe is to abstract away some of those unfamiliar cloud/distributed computing
details to let researchers focus on what they are familiar with (i.e. writing consistent
input and output schemas and the computation logic that transforms data from inputs into
outputs) while automating the boring but necessary work to run millions of simulations (e.g.
serializing data to and from cloud buckets, configuring queues, etc).

There are of course lots of data engineering orchestration tools out there already, but Scythe
is a bit more lightweight and hopefully a little simpler to use, at the expense of fewer bells and whistles (for now)
like robust dataset lineage, ui/ux for browsing previous experiments etc.

[Hatchet](https://hatchet.run) is already very easy (and fun!) to use for newcomers to
distributed computing, so I recommend checking out their docs - you might be better off
simply directly running Hatchet! Scythe is just a lightweight modular layer on top of it
which is really tailored to the use case of generating large datasets of consistently structured
experiment inputs and outputs. Another option you might check out would be something like [Coiled + Dask](https://coiled.io/).

## Context

### Motivation for writeup

I'm writing this for a few reasons -

- to condense some of the knowledge that I think is most useful for other people looking
  to get into large-scale distributed cloud computing (large at least in the context of
  academia, specifically engineering/applied ML fields, as opposed to say AI research) who
  might otherwise take a while to get up to speed on stuff, and/or who feel extensive pain trying
  to learn their institution's archaic and arcane supercomputing cluster patterns (ahem) when all
  they want to do is just run a shitload of simulations.
- to give back to and participate in the community of developers who share their experiences
  and challenges on the internet, and in so doing hopefully help at least one other person
  learn and grow, the way countless others have helped me with their blog posts, videos, tutorials,
  books, etc.
- to reflect on some of the work I've been doing in the course of my Masters/PhD that is not
  really relevant to reserach publications, but which is arguably more complex and valuable
  from a personal skill development perspective.

This is meant to be part dev-diary, part primer on using Scythe, and part primer on deploying
distributed computing applications in the cloud which I can share with classmates/colleagues.
Depending on your interests, you will probably want to skip various sections of it.

### Background

Buildings account for ~40% of global emissions, mostly via space heating snd cooling. My
research @ the MIT Sustainable Design Lab (School of Architecture+Planning) is focused on
decarbonizing the built environment by developing tools which leverage distributed computing
and machine learning to accelerate large-scale bottom up building energy modeling within retrofit
planning frameworks used by policymakers, utility operators, real estate portfolio owners, and
homeowners.

As part of that work, I often work on research projects/experiments for myself or colleagues
with anywhere from 1e3 to 1e7 building energy simulations, and so have had to develop workflows
which can handle operating at the requisite scale.

> _You are probably immediately wondering what the carbon cost of the research is. Across all
> the simulations I've invoked since starting in the early 2020s, assuming some carbon factors and PUE factors for the AWS us-east-1
> data center, I've estimated it to be equivalent something on the order of 1 month of emissions associated with a
> typical single family home in New England. <br><br> Definitely not nothing, but definitely small enough
> that if just one or two additional homes or businesses install a heat pump and do some airsealing
> that wouldn't have otherwise, it will make the research net carbon negative. Could there have been
> a better use for all that carbon spent on compute which might have resulted in even greater carbon leverage?
> Maybe - probably - but this is what I do and work on and enjoy, so for now I just hope for the best._

## Development history

Over the past few years, I've worked on and off on the system I use when I need to run
a few million simulations at a time, including rewriting things from the ground up a few
times. There's probably a component of that impulse to rewrite which is just wanting to try out a fancy new
thing I've learned about each time, another component which is wanting to grow as a
developer by re-evaluating and re-designing something to achieve the same goal but with
lessons learned and a better eye for what would be useful functionality, and finally a
component of that is to satisfy the desire to get things to a place where someone else
can actually take advantage of and make use of some of my work product in the open source
spirit.

- `vminus2`: Spring 2023: Earning the word `embarrassing`: embarrassingly parallel, and
  embarrassingly architected. Spin up a bunch of instances on [PaperSpace](https://paperspace.com)
  (now owned by DigitalOcean) each with very high numbers of CPUs, open up virtual desktop
  via web UI, use [tmux](https://github.com/tmux/tmux/wiki) to start 30-ish simulation
  processes per instance. Each process does ~1k-2k sims, writes an HDF file with all of its
  sim results to S3, eventually run a separate collector after completion to combine S3
  results.
- `vminus1`: Summer 2023 - Spring 2024: Roll my own. Use SQS to ingest a message for each
  different simuation, then spin up AWS Batch array job with a few thousand worker nodes
  (Fargate Spot) which chew through messages from the queue, exit after queue has been empty for
  some amount of time. Ugly attempts at dynamic leaf task invocation.
- `v0`: Summer 2024 - Spring 2025: Adopt a proper distributed asynchronous task framework - [Hatchet](https://hatchet.run) (v0) - as the async distributed
  queue instead of the lower level SQS. Abstract common/shared scatter/gather logic to decouple simulation
  fanout patterns from underlying leaf tasks. Still create Hatchet worker nodes via AWS Batch
  (Fargate Spot). Use AWS Copilot CLI (blech) if self-deploying Hatchet, but mostly use
  managed Hatchet.
- `v1`: Summer 2025+: Adopt Hatchet v1, fully isolate experiment creation/tracking into
  re-usable extensible patterns including middleware for things like data infiltration/exfiltration
  by creating [Scythe](https://github.com/szvsw/scythe)
  ([example usage](https://github.com/szvsw/scythe-example)). Create simpler self-hosting
  config via [sst.dev](https://sst.dev) in [HatchetSST](https://github.com/szvsw/hatchet-sst).

### The road(s) not taken...

Celery is the most popular and common async task queue for Python, but I wanted to stay away
from it for a variety of reasons I won't get into here. It would not have been a bad choice though.

There's probably one main alternative solution which _might_ be a better choice than what I have
settled on: [Coiled](https://coiled.io) + [Dask](https://dask.org). It's pretty easy to use,
setup, get started with, easy to spin up a ton of compute very quickly, etc. I think had
I come across Coiled earlier, I might have just gone that route. I didn't come across it until
Fall 2024, and I had already put substantial design time into the version using Hatchet,
so there was a bit of a sunk cost thing going on there, but I also just genuinely really
liked Hatchet's design decisions and the team from hatchet had already
been super fun and easy to work with as I was stress-testing some of their managed infra,
so I felt it was worth it to continue with Hatchet - as well as for a variety of other reasons which I
probably will not get into in this post. I guess one of them is that software stack at
the building/real estate decarbonization planning SaaS startup that that I do ML engineering
work at ([CarbonSignal](https://carbonsignal.com)) makes heavy use of Celery, and I would
like to eventually move us away from Celery to Hatchet if we ever do a refactor of the
async task management part of the stack, which we probably won't ("if it ain't broke..."),
but if we do I would at least like to be prepared to make an argument for switching.

There are of course other bits of tooling like Dagster, Airflow, Prefect etc that play a role
in workflow orchestration and data management, plus platforms like Weights & Biases or Neptune.ai
that play a role in experiment tracking (I actually really like WandB and use it at CarbonSignal),
but I think these are mostly overkill in the context I am most typically working
(academic experiments run once or twice a month - if that - with a few million tasks in
each experiment).

If you have other recommendations you think I should check out, would love to discuss!

### So why stick with Hatchet?

I would say the top things that I find most useful in Hatchet over say Celery, or my self-rolled
SQS queues, or something like Coiled+Dask or any of the other options I looked at are:

#### DAGs

Pretty great first class support for complex DAGs complete with detailed type-safety and payload validation.
I vastly prefer the design language here over Celery's mechanisms for building DAGs, and the
type safety via Pydantic is awesome, both at runtime and in dev (yes I know you can achieve
something similar with Celery but it is ugly). This was especially ugly in my early versions, where
I essentially would just have a worker track all of its results in memory and periodically
flush them to S3, rather than using a true scatter/gather DAG. It could also easily result
in lost compute if a node got shut down between flushes.

#### Retry/Durability in DAGs

Fantastic retry/durable handling in DAGs, which for me plays a key role in greatly reducing
costs by removing most of the annoyances that come with running on spot capacity. Most queues have some form of acking receipt
on finish/retrying tasks, so that if a spot capacity worker gets reclaimed by AWS, the message/task
will still get processed by another worker node, but the retry durability unique to Hatchet
is especially important in scatter/gather style-tasks - if I've already allocated 5e6 out of 1e7 simulations,
I definitely don't want that first half getting allocated again if a spot capacity worker gets reclaimed by AWS!

Hatchet will automatically resume allocating simulations where the previous worker node left off when the
allocation task gets picked up again. Similarly, during collection, let's 5% of the simulations had failed
due to an uploaded artifact which had bad data in it (e.g. a weather file from a faulty weather station).
I can easily just retry those directly, and retrigger collection of all results - since I use
a recursive subdivision tree pattern for scattering and gathering tasks, Hatchet only re-runs
the branches of the tree that actually needed to be rerun. This retry+durability support
makes it stress-free to use spot capacity, which GREATLY reduces costs.

#### Worker Tags

Being able to specify which node type a task should run on makes it a lot easier to efficiently
allocate compute. For instance, I know that my scatter/gather task needs relatively high memory
and benefits from multiple CPUs when it is assembling results files, while my leaf simulation
tasks are limited by essentially single core performance. I can easily just specify that
leaf tasks should be on 1vCPU/4GB nodes with an appropriate tag, and my scatter/gather task
need to be on 4vCPU/16GB nodes with an appropriate tag, and then when deploying cloud compute,
give the workers tags depending on what type of node they are on.

## Scythe - from a user perspective

Scythe is useful for running many parallel/concurrent simulations with a common I/O interface.
It abstracts away the logic of uploading and referencing artifacts, issuing simulations
and combining results into well-structured dataframes and parquet files.

After an experiment is finished, you will have a directory in your S3 bucket with the
following structure:

```
<experiment_id>/
├──── <version>/
│     ├──── <datetime>/
│     │     ├──── manifest.yml
│     │     ├──── experiment_io_spec.yml
│     │     ├──── input_artifacts.yml
│     │     ├──── specs.pq
│     │     ├──── artifacts/
│     │     │     ├──── <field-1>/
│     │     │     │     ├──── file1.ext
│     │     │     │     └──── file2.ext
│     │     │     └──── <field-1>/
│     │     │     │     ├──── file1.ext
│     │     │     │     └──── file2.ext
│     │     │     ...
│     │     ├──── scatter-gather/
│     │     │     ├──── input/
│     │     │     └──── output/
│     │     ├──── final/
│     │     │     ├──── scalars.pq
│     │     │     ├──── <user-dataframe>.pq
│     │     │     ├──── <user-dataframe>.pq
│     ├──── <datetime>/
├──── <version>/
...
```

In this example, we will demonstrate setting up a building energy simulation so we can
create a dataset of energy modeling results for use in training a surrogate model. In
fact, this experiment itself might just be one node in a larger DAG which handles automated
design space sampling, training, and progressively growing the training set + retraining
until error threshold metrics are satisfied. For now, we will just focus on a simple experiment
though.

To begin, we start by defining the schema of the inputs and outputs by inheriting from
the relevant classes imported from Scythe. The inputs will
ultimately be converted into dataframes (where the defined input fields are columns).
Similarly, the output schema fields will be used as columns of results dataframes
(and the input dataframe will actualy be used as a MultiIndex).

Note that `FileReference` inputs, which can be `HttpUrl | S3Url | Path`, which are of
type `Path` will automatically be uploaded to S3 and re-referenced as S3 URIs.

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

The schemas above will be exported into your results bucket as `experiment_io_spec.yaml`
including any docstrings and descriptions, following [JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/).

_nb: you can also add your own dataframes to the outputs, e.g. for non-scalar values
like timeseries and so on. documentation coming soon._

Next, we define the actual simulation logic. We will decorate the simulation function
with an indicator that it should be a part of our `ExperimentRegistry`, which configures
all of the fancy scatter/gather logic. Note that the function can only take a single
argument (the schema defined previously) and can only return a single output instance of
the previously defined output schema (though additional dataframes can be stored in the
`dataframes` field inherited from the base `ExperimentOutputSpec`.).

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
| ------------- | ---------- | -------------------- | ------: | --: | -------: |
| bem/v1        | 0          | abcd-efgh            |     5.2 | 2.7 |     23.5 |
| bem/v1        | 1          | abcd-efgh            |     2.9 | 1.3 |     19.7 |
| bem/v1        | 2          | abcd-efgh            |     4.2 | 5.4 |     21.4 |

`Data`

| heating | cooling | lighting | equipment | fans | pumps |
| ------: | ------: | -------: | --------: | ---: | ----: |
|    17.2 |    15.3 |     10.1 |      13.8 | 14.2 |   1.4 |
|    21.7 |     5.4 |      9.2 |       5.8 | 10.3 |   2.0 |
|    19.5 |     8.9 |     12.5 |      13.7 |  8.9 |   0.9 |

**_TODO: document how additional dataframes of results are handled._**

Additionally, in your bucket, you will find a `manifest.yml` file as well as an `input_artifacts.yml` and `experiment_io_spec.yml`.

```yaml title="manifest.yml"
experiment_id: building_energy/v1.0.0/2025-07-23_12-59-51
experiment_name: scythe_experiment_simulate_energy
input_artifacts: s3://mit-sdl/scythe/building_energy/v1.0.0/2025-07-23_12-59-51/input_artifacts.yml
io_spec: s3://mit-sdl/scythe/building_energy/v1.0.0/2025-07-23_12-59-51/experiment_io_spec.yml
specs_uri: s3://mit-sdl/scythe/building_energy/v1.0.0/2025-07-23_12-59-51/specs.pq
workflow_run_id: f764ef33-a377-4572-a398-a2dc56a0810f
```

```yaml title="input_artifacts.yml"
files:
  design_day_file:
    - s3://mit-sdl/scythe/building_energy/v1.0.0/2025-07-23_12-59-51/artifacts/design_day_file/USA_MA_Boston.Logan_TMYx.ddy
    - s3://mit-sdl/scythe/building_energy/v1.0.0/2025-07-23_12-59-51/artifacts/design_day_file/USA_CA_Los.Angeles.LAX_TMYx.ddy
  weather_file:
    - s3://mit-sdl/scythe/building_energy/v1.0.0/2025-07-23_12-59-51/artifacts/weather_file/USA_MA_Boston.Logan_TMYx.epw
    - s3://mit-sdl/scythe/building_energy/v1.0.0/2025-07-23_12-59-51/artifacts/weather_file/USA_CA_Los.Angeles.LAX_TMYx.epw
```

```yaml title="experiment_io_spec.yml"
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

## Scythe - from a developer perspective

### Requirements

The key design requirement that I wanted to satisfy was to make it easy for an academic/engineer
to quickly define what the interface and business logic of a single experiment task would be
and then quickly convert that into a massively parallel experiment with well structured,
pre-collected outputs. This means we will want to be able to automatically detect and
serialize both inputs and outputs into a dataframe-like format. It also means we will want
to automatically handle serializing local artifacts required by simulations into S3 (for me,
these might be boundary condition specs, like the `.epw` format weather files used in building
simulations). We also want good records of what the specifications for the experiment were,
both at the interface level (i.e. what was the configuration/meaning of inputs and outputs)
and at the instance level (which specific values of the interfaces' inputs were used).

### Divide and Conquer

Scythe uses a divide-and-conquer strategy to maximize allocation/collection throughput with
recursive subdivision. Let's understand why it helps by working through an example.

Let's say we have 1e7 simulations to run, and each simulation takes 2-3 seconds to complete.

We will have some worker nodes which are responsible for taking the specifications for all simulations
from a parquet file and enqueuing the simulations, and then a much larger pool of worker nodes
which are responsible for executing the simulations; the enqueuing workers will also be
responsible for gathering and combining results.

Now let's suppose we can add simulations to Hatchet's queue at approximately a rate of 100
tasks/s from a single enqueuing worker. It will take that worker 1e5s ~= 1 day to enqueue all the
tasks. More problematic though is that if we spin up 400 worker nodes, we will be completing
on average 400 tasks every 2.5 seconds, or an average of 160 tasks/second. Except we only have
100 tasks reaching the queue per second, and we will be bottlenecked with lots of compute nodes
sitting idle! How can we get around this?

We can get around it by recursively subdividing the original batch of 1e7 simulations into smaller
batches, which in turn either get subdvided again or if the recursion base case tripwire is
triggered, then the remaining batch gets added to the queue as actual simulations to run.

As an example, let's consider a single subdivision level with a branching factor of 10. The
root scatter/gather task will download the complete experiment specs parquet file from S3,
break it up into 10 equally sized pieces (or 9 equally sized pieces + some left overs),
and then create children tasks which perform the scatter/gather logic on the trimmed batches.
Since we only set a single subdivision level, these children will be responsible for actual
adding the individual task specs for the simulations to the Hatchet queue. This means we
now have 10 children scatter/gather tasks, which each have 1e6 simulations to enqueue, which,
assuming the engine can handle the additional worker throughput, means 1000 tasks/s enqueued. This
means we can now bump up to 2500 leaf simulation worker nodes, which would average 1000 tasks
completed per second since tasks take an average of 2.5s. Our entire experiment of 1e7
runs should be completed in 2 hours and 45 min, give or take.

Now, suppose we choose to instead use two levels of recursive subdivision. Then we will end
up with 100 enqueuing workers, which would mean 10k tasks/s enqueued (if the engine can handle
it), and we could theoretically use 25k workers, and be done in 15 minutes. However, realistically,
you probably will be limited by your AWS service quota at something like 5k-10k worker nodes.
Additionally, the Hatchet engine, if self-deployed, might not be able to support 10k tasks/s
enqueuing or finishing. However, there are still significant benefits to using a higher branching
factor when it comes to collecting results.

When a terminal scatter/gather task is collecting its leaf/children simulation tasks' results,
it's pulling them directly from Hatchet, and we will be limited by whatever the throughput there is.
However, it will combine those results into a parquet file(s), which will be serialized
and sent to S3 and the scatter/gather task will return a thin payload with an S3 URI(s).
The predecessor scatter/gather task in the tree will be responsible for collecting the S3 URIs
of its children, retrieving them from s3, combining them, and then serializing the combined
version back to S3, and passing a thin payload output up the tree, until eventually we
get to the root scatter gather task. This is where the recursive subdivision really shines,
as it can greatly reduce the amount of time it takes to collect and combine results by breaking
it up into parallelized tasks, especially since we can use ThreadPoolExecutors to parallelize the
network-bound process of pulling the children's thin URI payloads from S3.

### Dealing with thick & thin payloads

Hatchet's task payload size is limited to something like 4MB (correct me if I'm wrong @hatchet-dev team!).
This means that if we are 1e6 simulations, we most likely would not be able to submit the
task as the payload containing all of the information for all of the simulations would be
too large. The typical way around this is to serialize the payload, store it somewhere else,
and then submit a reference to that payload in the actual scatter/gather fanout task spec.

In an earlier version, I allowed the scatter/gather input spec to accept _either_ a list of
task specs _or_ a reference to a file containing all the task specs, but some of the code
around that got pretty gross, so in the latest version I decided to only support S3 URIs.

```py
class ScatterGatherInput(BaseSpec):
    """Input for the scatter gather workflow."""

    task_name: str = Field(..., description="The name of the Hatchet task to run.")
    specs_uri: S3Url = Field(..., description="The path to the specs to run.") # (1)!

    ... # (3)!


    @cached_property
    def specs(self) -> list[ExperimentInputSpec]: # (2)!
        """Fetch the specs and convert to the input type."""
        local_path = self.fetch_uri(self.specs_uri, use_cache=True)
        df = pd.read_parquet(local_path)
        specs_dicts = df.to_dict(orient="records")
        validator = self.standalone.input_validator
        return [validator.model_validate(spec) for spec in specs_dicts]

```

1. This is where we pass in a URI which which stores the complete set of leaf task specifications.
2. We can now access a cached, opened version of the full spec list inside of a scatter/gather task with `payload.specs`
3. Additional fields and methods omitted for brevity.

We also do something similar with results outputs - while each individual simulation/experiment
task can safely return a Pydantic model containing the actual results, as soon as we start
combining the results of multiple experiments, we will exceed the output payload size,
so we use the same "thin" payload approach.

If a scatter/gather task is a terminal node which actually allocated the leaf experiment
tasks, then when it is done, it simply combines the results of all of the children tasks
into a dataframe (or dataframes if the user also added user-defined dataframes to the
corresponding key of the output model); these get uploaded to S3 in an "intermediate results"
section of the experiment's directory within the bucket. It returns a reference to each
of the dataframes it wrote to S3. Then, a predecessor scatter/gather tasks on earlier
levels of the tree simply collect the dataframes generated by each of _its_ children
scatter/gather tasks, combines them, writes to S3, and returns URIs. The root scatter/gather
task then ultimately does the exact same thing, resulting in a single set of dataframes
with results from every simulation, e.g. one dataframe for all of the scalars, and one
dataframe for each of the custom user-defined dataframes in the task output.

If each simulation generates large amounts of data (e.g. high-resolution hourly timeseries
data or images), then the user can use the utilities inside of the base `ExperimentInputSpec`
class to write those to an appropriately namespaced/scoped location in the experiment directory
and return a reference to those files, creating their own datalake that they can later pull from.

_TODO: document writing out user files_

### Artifact Infiltration & Results Exfiltration

_TODO: automatic upload, caching inside of tasks, etc._

### Scalars dataframe construction

## Cloud Infrastructure

This will assume that you have at least some knowledge of
[Docker](https://docker.com) and containers, but otherwise will try to introduce you to
some of the key parts of the cloud deployment - and really cloud computing in general. It
covers some stuff that's pretty boring but it's not something that you will really learn
in the normal course of your academic research, and it's ultimately relatively simple to
at least get to working knowledge with, so I think it's worth covering here.

### Containerization

> (skip to [Deploying Containers](#deploying-containers) if you are familiar with Docker
> but not ECS, otherwise skip this section entirely and go to [Self-hosting](#self-hosting-hatchet-as-an-intro-to-cloud-configuration))

> The Docker documentation is extensive and great, especially the
> [Getting Started Guide](https://docs.docker.com/get-started/), so I recommend you start
> there. There are also countless guides online. Still, I think it is worthwhile to try
> to condense everything in one place so you get a good understanding of how all the pieces
> fit together.

If you work in academia, you are probably familiar with Python tools like
[Conda](https://anaconda.org/anaconda/conda), [uv](https://astral.sh/uv), and
[Poetry](https://python-poetry.org), or if you are coming from the web world you are probably familiar with npm/pnpm.
All of these enable you to consistently define and to some extent package the dependencies
of your project so that you can, hopefully, on another machine, easily reproduce the _environment_ you used
to write your software and still have your code run. There are of course still all sorts of
issues you might run into, like needing Python + Conda/uv/Poetry or Node + npm/pnpm installed,
their might be incompatibilities with the version of Python/Node or the other machine's architecture,
etc. uv and nvm/pnpm do help with these, but it still can be a pain. Plus, there might
be all sorts of other dependencies which cannot be captured by those tools, like, for me,
[EnergyPlus](https://energyplus.net/), the de facto standard for building energy model simulation
in practice and academia (developed and maintained by the DoE and NREL).

Docker images and containers address this exact issue. You can think of
_images_ as a pre-built artifact which contains everything you need to run a _container_,
which you can think of (even if it's not exactly true) an isolated, mini virtual machine
that has everything installed and working perfectly already, letting you easily reproduce
an entire application, including any necessary dependencies, environment variables, system
libraries, binaries, etc. Think of it like shipping your lab experiment in a fully
stocked portable lab that can run identically anywhere, no matter the underlying hardware
or OS. This means that images + containers are the de-facto standard for deploying applications
in the cloud - you just need to tell your cloud infrastructure "hey go fetch this image
and run it in a container." You typically store the containers in a repository which lets
you define different tags, i.e. versions, as it evolves over time, just like GitHub. The
most common container registry to use is probalby _Elastic Container Registry_ [(_ECR_)](https://aws.amazon.com/ecr/) on
AWS of _GitHub Container Repository_ [(_GHCR_)](https://ghcr.io).

You define the image of a container using a _Dockerfile_, which typically starts by inheriting
from another image (typically based off of some lightweight Linux distributino) which
has most of what you need already, like Python etc. Then, you copy over your project files,
install anything you need to, and set what command should run when a container for this
image is started up.

#### Dockerfile example

Let's take a look at this in practice. Suppose we have a standard Python repo which uses
`uv` for its dependency management. There's a `pyproject.toml` file which configures
our project as usual, along with a `uv.lock` file which has all the precise dependency
version information locked, and then some code in our `experiments/` dir and a `main.py`
file which looks like this:

```py title="main.py"
from scythe.worker import ScytheWorkerConfig

from experiments import *  # import the experiments so that they get auto-registered


if __name__ == "__main__":
    worker_config = ScytheWorkerConfig()
    worker_config.start()
```

In the following Dockerfile, we inherit from a lightweight image with
Python pre-installed, then we copy over the binaries for `uv` from a pre-existing image
released by Astral, the creators of `uv`. Then we copy over anything from our codebase
we need, install our Python dependencies with `uv`, and then, specify what command to run
when starting a container up with this image.

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

We can build this container with `docker build -f path/to/your/Dockefile .`

Once the image is built, we can run it, tag it, push it to a repository, etc. However,
generally, we use our infrastructure-as-code or CI/CD tooling to manage that for us.

#### Docker Compose example

Often times, we need multiple containers running at the same time - maybe a frontend and
a backend, or in our case, the Hatchet task system - which itself needs a few containers for
its different components like a database, broker, engine, dashboard, etc. That's
where
[_Docker Compose_](https://docs.docker.com/get-started/docker-concepts/running-containers/multi-container-applications/)
comes in. We use `docker compose` to run multiple containers at the same time, including
setting up a network for them to talk to each other, setting up volume mounts to persist
information even after we spin the containers down, allowing ports on your host machiine to
be routed into ports in specific containers etc. The configuration for running multi-container
applications is done in a file typically called `docker-compose.yml`. Here's an example
which just specifies running our a single container for our worker, which we assume will
be connecting to our cloud instance of Hatchet via an API token specified in the `.env` file:

```yaml title="docker-compose.yml"
services:
  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
      args:
        - PYTHON_VERSION=${PYTHON_VERSION:-3.12}
    env_file:
      - .env
    deploy:
      mode: replicated
      replicas: 1
```

We can run this with a simple `docker compose up`. If we want to run more copies of the
worker, we can also easily bump the `replicas` up to `n`. However, We might also want to stand
up Hatchet locally, in which case we can follow the instructions from [Hatchet's official docs](https://docs.onhatchet.run/self-hosting/hatchet-lite)
and create a second file called `docker-compose.hatchet.yml` with their provided contents.

We can run both the container and the worker using the following command:

```sh
docker compose -f docker-compose.yml -f docker-compose.hatchet.yml up
```

#### Deploying containers

Now that you have a solid mental model of containerization (hopefully), let's briefly talk about how
containers are used in a cloud application. Typically, you have some form of CI/CD pipeline
which is resposnible for testing your code, building containers, and pushing to a repository.

Then, when you deploy your infrastructure, your cloud provider will pull the images from
the repository and run however many of them you ask for - maybe it's controlled by some auto-scaling
logic. In my case, I generally just manually set "a shitload of containers" - e.g. 5000 -
when I am starting an experiment run and then manually set it to "0" when the experiment is
done, rather than worrying about relying on auto-scaling logic which might accidentally
run up a huge bill if it fails to scale down. One reason I like AWS Batch/Fargate is that
you can set a timeout for an entire array job (array as in many fargate instances running the
same container) so there is a safeguard in place that will automatically shut down all containers.

Another common way of controlling costs is to use `spot` capacity, where your instances
running your containers come at roughly 1/4th the price and are put on machines which are
effectively idling in your cloud provider's data center, BUT they can be terminated at any
time if on-demand customers need them. Typically when this happens, you just get another
instance automatically spun up as soon as its available. Lucky for us, Hatchet's
robust failure/retry handling makes this a complete non-issue - it's totally fine if a
worker goes offline in the middle of a task.

Probably the easiest way to get started with deploying containers in AWS is by using
_Elastic Container Service_ ([_ECS_](https://aws.amazon.com/ecs/)). This is a little bit
of a simplification, but you can think of ECS as, essentially, just a way of replicating
what Docker Compose does but in the cloud. You define a _cluster_, which can have multiple
_services_. A cluster is backed by compute instances, like EC2, but I typically use Fargate
so that you do not have to worry about actually having a compute cluster backing the service cluster.
Each service in the cluster can be thought of, roughly, as the equivalent of a docker-compose file -
i.e. it can contain multiple containers which you specify images for, commands, environment variables,
exposed ports, etc. Each _task_ within a service is just a replica of that service's task
definition. So if we want 3000 copies of our worker node, we can just specify to run
3000 copies of the relevant service/task.

### Building a mini-cluster with your lab desktops' overnight spare cycles

### Self-hosting Hatchet as an intro to cloud configuration

While I actually think there's a good chance you are likely to be better off using
[the managed Hatchet cloud](https://hatchet.run) (see my price comparison with self-hosting
[here](https://github.com/szvsw/hatchet-sst?tab=readme-ov-file#cost-estimate)), if we
are looking at what it takes to stand up an open source experiment tracking engine, I
don't think it would be right to do so while relying on managed infra (as wonderfully
easy and convenient as it is)! Plus, for my use-case of simply running a few million
simulations once or twice a month, it's only about $13/day to run the Hatchet engine and then tear
it down when done (rather than paying for the entire stack monthly or for the managed cloud).

[Hatchet](https://github.com/hatchet-dev/hatchet) is composed of a few pieces - a broker
(RabbitMQ), a database (Postgres), the engine (written in Go - this is where most of
Hatchet's magic happens), a web dashboard (Next) and an API (also in Go). The Hatchet
team has written a bunch of really
[great blog posts](https://docs.hatchet.run/blog/multi-tenant-queues) which give you a peek
into the underlying infrastructure, including some of the benefits of using pg as part of
an async queue stack. The [release notes](https://github.com/hatchet-dev/hatchet/releases/tag/v0.55.26)
also often include a lot of cool technical details which I encourage you to check out as well.

The official [Hatchet self-hosting docs](https://docs.onhatchet.run/self-hosting) already
include deployment instructions for Kubernetes/Helm, but I do not have real experience with
them, so I instead went the route of building out my own infra. The actual
infrastructure-as-code for self-deploying Hatchet that I wrote is all done with
[sst.dev](https://sst.dev) + [Pulumi](https://pulumi.com), and can be found with a bunch
of detailed instructions in the [szvsw/hatchet-sst](https://github.com/szvsw/hatchet-sst)
repository. This was my first time using both SST & Pulumi, but I have experience with
Terraform as well as AWS Copilot CLI+CloudFormation (blech) as well as plenty of experience
just doing things manually in the console, so picking up SST/Pulumi was straightforwrd enough.

After reading this section, you should have enough knowledge to dive into
[szvsw/hatchet-sst](https://github.com/szvsw/hatchet-sst) and start customizing things to
your liking or ripping things out and replacing - or even just rebuilding things on your own
in the AWS Console.

So, let's get into it!

#### The VPC

When you are at home, you have a whole bunch of resources which all need to talk to each
other, and possibly the internet - your laptop, your smart TV, your cell phone, your printer,
etc. They all sit behind your router and form a network where the devices can talk to
each other via the router without sending messages out over the internet, while some of
them can additionally send or even receive messages from the big internet beyond through
the router. We can think of this cluster of devices as a local private cloud.

On AWS, a _Virtual Private Cloud_ (_VPC_) can be thought of similarly - it's just where
all of the different pieces of your infrastructure live in a shared network so that they
can find each other and (possibly) talk to the internet, with lots of configurability for
how the resources are allowed to (or not!) communicate with each other, what kinds of traffic
they are allowed to receive, how exposed they are to the internet, etc.

Our VPC itself lives inside of a _region_, which is just AWS parlance for "a bunch of
datacenters in a particular location, e.g. North Virginia" (`us-east-1` stans rise up).
Because, for some unknown, mysterious-to-me reasons, these datacenters very occasionally
like to take a mental health day, each region will have a few different
_availability zones_ (_AZs_), (e.g. `us-east-1a` or `us-east-1b`) which are really just
specific subgroups of the actual datacenter buildings within the same region that are
nevertheless separated by enough distance to at least not be affected by the same tornado
(yes, that seems to be an official metric, at least according to the
[AWS marketing](https://aws.amazon.com/about-aws/global-infrastructure/regions_az/)). I
like to think of them as being close enough to support the same professional sports teams
but different high school sports teams. It's pretty common practice when setting up your
VPC to specify that it will use two or three availability zones, but for our purposes we
could probably get away with one. For the types of computing I do, I've never really had
to think about AZs much, besides a few pieces of infrastructure which scale their cost
with the number of AZs (like PrivateLink VPC Endpoints).

When the VPC gets created, it typically gets one _private subnet_ and one _public subnet_
created for each AZ. Resources in the VPC can always find and talk to each other, but
resources in the private subnet cannot cannot reach or be reached by the outside internet
(by default - they can in fact reach the internet with some extra bits and bobs attached) while
resources in the public subnet can automatically reach the external internet (though
not necessarily be reached by it). This is a little bit of a simplification, but it's
the mental model I've always used and it has worked for me. You can think of this as if
you had two routers set up at home, both connected to each other, but only one of them
connected to your internet provider. You might put a device like your printer on the router
that's not connected to the internet, while you would put your smart TV on the one that is.
Of course you could set up some extra tooling to allow you to say, trigger a printout on your home
printer from work, but it would require following specific patterns to do so.

#### Public vs Private Subnets

> _nb: we use the term `egress` when the resource in question is initiating connections to
> some other resource and receiving a response, while `ingress` would indicate that the resource
> in question is open to connections initiated by some other resource and providing responses.
> At least that's how I think of it!_

Let's think through which subnets to use for each of our resources:

| Resource          | Subnet            | Reasoning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ----------------- | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Database          | Private           | The database does definitely does not need any internet egress or ingress. It just needs to be reachable inside the VPC by the Hatchet engine/API.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| Broker            | Private           | Same as the db.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Load Balancer     | Public            | The load balancer will be responsible for routing internet ingress traffic from worker nodes (e.g. deployed locally on your machine) to the engine or API containers, or user traffic on the web UI dashboard to the dashboard container. As such, it definitely needs to be in the public subnet.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| Hatchet Engine    | Public or Private | The engine does not inherently need internet egress during operations, so we can definitely put it in a private subnet if we want; however, the service does need to pull container images from Elastic Container Registry (ECR) before starting up, and by default that requires internet egress even though ECR is still in the AWS region; however if we want the engine in a private subnet, we can just add a NAT Gateway or AWS PrivateLink VPC endpoints to allow the private subnet to reach ECR. Now you might be thinking - well, these services might need internet ingress so that local workers outside of the VPC can talk to the engine, and you would be right - but since we are using a load balancer to front the application, the load balancer can be in the public subnet while then routing traffic to the appropriate targets in the private subnet. |
| Hatchet Dashboard | Public or Private | Same as above.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |

#### Security Groups

_Security groups_ (_SGs_) are just the logical groupings with rules that allow you to easily define which resources in your
subnet are allowed to talk to which other resources. A security group can have both ingress
and egress rules - who will this group accept incoming traffic from and on what ports/protocol?
Who is this group allowed to send outgoing traffic to and on what ports/protocol? For instance,
suppose you have an EC2 compute instance up in a public subnet with a public IP address assigned
which you want to allow yourself to SSH into. You could create a security group to place
that instance inside of which has a rule that says "allow ssh traffic via TCP/port 22 from _my IP address_",
(AWS helpfully has a button you can click to resolve your personal IP address automatically).

To keep things simple then, we can just create a default security group that allows each service to send
outbound traffic to any IP on any port and allow inbound traffic on any port but only from
IPs which are inside the VPC. Note that just because the security group allows outbound traffic
doesn't mean every resource can reach the internet (e.g. those in the subnet have no path) -
it just means if it tries to make one such request, it won't get blocked by the security
group's rules. Now this is pretty permissive, even if each resource is only accepting traffic inside
the VPC. Of course, we could be much more precise (less permissive) without much more difficulty:

Clearly, both the Database and the Broker need ingress allowed from the Engine. The Dashboard (which
also includes the API) needs to be able to talk to the Database and possibly the Engine.
The Engine possibly needs to be able to talk to the API. To do that, we just need to
set up specific security groups for each of the resources, and then create the relevant in-
or egress rules. I've done that for the Broker for instance, but am still using the default
SG outlined above for everything else. Want to contribute to [szvsw/hatchet-sst](https://github.com/szvsw/hatchet-sst)?
That would be a great and easy first PR!

#### Deploying the Hatchet service

### Worker nodes

#### Deploying a lot of workers at once

#### Differentiating worker types
