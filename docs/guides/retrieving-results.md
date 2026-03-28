# Retrieving Results

This guide explains the structure of experiment outputs and how to programmatically access results.

## S3 Output Structure

After a successful experiment run, Scythe writes the following to S3:

```
<bucket_prefix>/<experiment_name>/<version>/<timestamp>/
├── manifest.yml
├── experiment_io_spec.yml
├── input_artifacts.yml
├── specs.pq
├── workflow_spec.yml               # single-spec runs only
├── artifacts/
│   └── <field_name>/
│       ├── file1.ext
│       └── file2.ext
├── scatter-gather/                  # batch runs only
│   ├── input/
│   └── output/
├── final/                           # batch runs only
│   ├── scalars.pq
│   ├── result_file_refs.pq
│   └── <user_dataframe>.pq
└── results/
    └── <field_name>/
        ├── <run_id_1>.ext
        └── <run_id_2>.ext
```

### Key Output Files

| File                        | Description                                                                |
| --------------------------- | -------------------------------------------------------------------------- |
| `manifest.yml`              | Run metadata: experiment ID, workflow run ID, S3 URIs for specs and schema |
| `experiment_io_spec.yml`    | JSON Schema describing the input and output types                          |
| `input_artifacts.yml`       | S3 URIs of all uploaded input artifact files                               |
| `specs.pq`                  | All input specs serialized as a Parquet file                               |
| `final/scalars.pq`          | Scalar output fields from all tasks, with a MultiIndex from input specs    |
| `final/result_file_refs.pq` | S3 URIs of output file references, with the same MultiIndex                |
| `final/<name>.pq`           | User-defined DataFrames (from `ExperimentOutputSpec.dataframes`)           |
| `results/<field>/<id>.ext`  | Individual output files from `FileReference` output fields                 |

## Result DataFrames

### scalars.pq

The primary output file. Its structure is:

**MultiIndex** (from input spec fields):

| experiment_id  | sort_index | root_workflow_run_id | temperature | pressure | material |
| -------------- | ---------- | -------------------- | ----------- | -------- | -------- |
| exp/v1.0.0/... | 0          | abc-123              | 300.5       | 1.2e6    | steel    |
| exp/v1.0.0/... | 1          | abc-123              | 250.0       | 5.0e5    | aluminum |

**Data columns** (from output spec scalar fields):

| energy | efficiency |
| ------ | ---------- |
| 42.0   | 95.0       |
| 38.5   | 91.2       |

If your `ExperimentInputSpec` subclass overrides `computed_features`, those derived values also appear as additional index levels (between the Pydantic fields and any `additional_index_data`).

Fields that cannot be represented in a pandas MultiIndex (e.g., `FileReference`, lists, dicts) are automatically excluded from the index.

### result_file_refs.pq

Has the same MultiIndex as `scalars.pq`, with columns for each `FileReference` output field containing S3 URIs:

| report                             | raw_data                            |
| ---------------------------------- | ----------------------------------- |
| s3://bucket/results/report/abc.pdf | s3://bucket/results/raw_data/abc.h5 |
| s3://bucket/results/report/def.pdf | s3://bucket/results/raw_data/def.h5 |

## Programmatic Access

### List Experiment Versions

```python
from scythe.experiments import BaseExperiment
from my_experiments import simulate_energy

experiment = BaseExperiment(runnable=simulate_energy)

# List all versions
versions = experiment.list_versions()
for v in versions:
    print(v.version)  # e.g. SemVer(major=1, minor=2, patch=0)
```

### Get the Latest Version

```python
latest = experiment.latest_version()
print(latest.version)  # e.g. v1.2.0
```

### List Runs for a Version

```python
runs = latest.list_runs()
for run in runs:
    print(run.experiment_id, run.timestamp)
```

### Get Result File Keys

```python
# Latest results across all versions
results = experiment.latest_results
# {"scalars": "prefix/.../final/scalars.pq", "result_file_refs": "prefix/.../final/result_file_refs.pq", ...}

# Results for a specific version
from scythe.experiments import SemVer
results = experiment.latest_results_for_version(SemVer(major=1, minor=0, patch=0))
```

### Download and Load Results

```python
import boto3
import pandas as pd

s3 = boto3.client("s3")
bucket = "my-bucket"

# Download scalars
s3.download_file(bucket, results["scalars"], "scalars.pq")
df = pd.read_parquet("scalars.pq")

print(df.head())
print(df.index.names)  # MultiIndex column names from input spec
```

### Using ScytheStorageSettings

For convenience, you can read the bucket configuration from environment variables:

```python
from scythe.settings import ScytheStorageSettings

settings = ScytheStorageSettings()
print(settings.BUCKET)         # e.g. "my-research-bucket"
print(settings.BUCKET_PREFIX)  # e.g. "scythe"
```

## Manifest Files

### manifest.yml

```yaml
experiment_id: simulate_energy/v1.0.0/2025-07-23_12-59-51
experiment_name: scythe_experiment_simulate_energy
workflow_run_id: f764ef33-a377-4572-a398-a2dc56a0810f
specs_uri: s3://bucket/scythe/simulate_energy/v1.0.0/2025-07-23_12-59-51/specs.pq
io_spec: s3://bucket/scythe/simulate_energy/v1.0.0/2025-07-23_12-59-51/experiment_io_spec.yml
input_artifacts: s3://bucket/scythe/simulate_energy/v1.0.0/2025-07-23_12-59-51/input_artifacts.yml
```

### experiment_io_spec.yml

Contains the JSON Schema for both input and output types, including field descriptions, types, and validation constraints. This provides a machine-readable record of the experiment's interface.

### input_artifacts.yml

Lists all uploaded input artifact files, organized by field name:

```yaml
files:
  weather_file:
    - s3://bucket/scythe/.../artifacts/weather_file/Boston.epw
    - s3://bucket/scythe/.../artifacts/weather_file/LA.epw
  design_day_file:
    - s3://bucket/scythe/.../artifacts/design_day_file/Boston.ddy
    - s3://bucket/scythe/.../artifacts/design_day_file/LA.ddy
```
