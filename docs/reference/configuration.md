# Configuration Reference

Scythe is configured entirely through environment variables, using [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for validation and type coercion.

## Storage Settings

Configured via `ScytheStorageSettings` (prefix: `SCYTHE_STORAGE_`):

| Variable                       | Type  | Default    | Required | Description                                      |
| ------------------------------ | ----- | ---------- | -------- | ------------------------------------------------ |
| `SCYTHE_STORAGE_BUCKET`        | `str` | --         | Yes      | The S3 bucket name for storing experiment data   |
| `SCYTHE_STORAGE_BUCKET_PREFIX` | `str` | `"scythe"` | No       | Key prefix within the bucket for all Scythe data |

All experiment data is stored under `s3://<BUCKET>/<BUCKET_PREFIX>/`.

## Timeout Settings

Configured via `TimeoutSettings` (prefix: `SCYTHE_TIMEOUT_`):

| Variable                                  | Type       | Default | Description                                                        |
| ----------------------------------------- | ---------- | ------- | ------------------------------------------------------------------ |
| `SCYTHE_TIMEOUT_SCATTER_GATHER_SCHEDULE`  | `Duration` | `1h`    | Maximum time for a scatter/gather task to be picked up by a worker |
| `SCYTHE_TIMEOUT_SCATTER_GATHER_EXECUTION` | `Duration` | `1h`    | Maximum execution time for a scatter/gather task                   |
| `SCYTHE_TIMEOUT_EXPERIMENT_SCHEDULE`      | `Duration` | `1h`    | Maximum time for an experiment task to be picked up by a worker    |
| `SCYTHE_TIMEOUT_EXPERIMENT_EXECUTION`     | `Duration` | `1m`    | Maximum execution time for an experiment task                      |

`Duration` values accept Hatchet duration strings like `"30s"`, `"5m"`, `"2h"`, `"1d"`, or Python `timedelta` objects.

!!! note
The `EXPERIMENT_SCHEDULE` and `EXPERIMENT_EXECUTION` timeouts are defaults used by `@ExperimentRegistry.Register()`. You can override them per-experiment using the `schedule_timeout` and `execution_timeout` parameters of the decorator.

### Timeout Guidance

- **Schedule timeouts** should be generous -- they cover the time a task waits in the queue. If workers are scaling up from zero, this can take minutes.
- **Execution timeouts** should be set based on the expected runtime of your longest simulation, with some headroom.
- **Scatter/gather timeouts** should account for the time to run all child tasks, since the parent waits for all children to complete.

## Worker Settings

Configured via `ScytheWorkerConfig` (prefix: `SCYTHE_WORKER_`):

| Variable                      | Type          | Default       | Description                                             |
| ----------------------------- | ------------- | ------------- | ------------------------------------------------------- |
| `SCYTHE_WORKER_NAME`          | `str \| None` | Auto-detected | Custom name for the worker (shown in Hatchet dashboard) |
| `SCYTHE_WORKER_SLOTS`         | `int \| None` | CPU count     | Number of concurrent task slots                         |
| `SCYTHE_WORKER_DURABLE_SLOTS` | `int \| None` | `1000`        | Number of durable (persistent) task slots               |
| `SCYTHE_WORKER_HIGH_MEMORY`   | `bool`        | `False`       | Advertise this worker as having high memory             |
| `SCYTHE_WORKER_HIGH_CPU`      | `bool`        | `False`       | Advertise this worker as having high CPU                |
| `SCYTHE_WORKER_HAS_GPU`       | `bool`        | `False`       | Advertise this worker as having a GPU                   |
| `SCYTHE_WORKER_DOES_FAN`      | `bool`        | `True`        | Whether this worker handles scatter/gather tasks        |
| `SCYTHE_WORKER_DOES_LEAF`     | `bool`        | `True`        | Whether this worker handles experiment (leaf) tasks     |

### Worker Name Auto-Detection

If `SCYTHE_WORKER_NAME` is not set, the name is generated based on the hosting environment:

| Environment Variable        | Detection   | Name Pattern                    |
| --------------------------- | ----------- | ------------------------------- |
| `AWS_BATCH_JOB_ARRAY_INDEX` | AWS Batch   | `ScytheWorker--AWSBatch<index>` |
| `COPILOT_ENVIRONMENT_NAME`  | AWS Copilot | `ScytheWorker--AWSCopilot<ENV>` |
| `FLY_REGION`                | Fly.io      | `ScytheWorker--Fly<REGION>`     |
| _(none)_                    | Local       | `ScytheWorker--Local`           |

### Slot Calculation

If `SCYTHE_WORKER_SLOTS` is not set:

- Machines with < 8 CPUs: `slots = cpu_count`
- Machines with >= 8 CPUs: `slots = cpu_count - 1`

## Hatchet Settings

These are standard Hatchet SDK environment variables (not Scythe-specific):

| Variable                      | Description                                   |
| ----------------------------- | --------------------------------------------- |
| `HATCHET_CLIENT_TOKEN`        | Authentication token for the Hatchet instance |
| `HATCHET_CLIENT_TLS_STRATEGY` | TLS strategy (`none`, `tls`, `mtls`)          |

See the [Hatchet SDK documentation](https://docs.hatchet.run) for the full list of client configuration options.

## AWS Settings

Standard AWS SDK environment variables used by boto3 for S3 access:

| Variable                | Description                                        |
| ----------------------- | -------------------------------------------------- |
| `AWS_REGION`            | AWS region for the S3 bucket                       |
| `AWS_ACCESS_KEY_ID`     | AWS access key                                     |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key                                     |
| `AWS_SESSION_TOKEN`     | (Optional) Session token for temporary credentials |
| `AWS_PROFILE`           | (Optional) Named profile from `~/.aws/credentials` |

Workers running on AWS (ECS, EC2, Lambda) can use IAM roles instead of explicit credentials.

## Example .env File

```sh title=".env"
# Hatchet
HATCHET_CLIENT_TOKEN=eyJhbGciOiJFUzI1NiIs...

# AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...

# Storage
SCYTHE_STORAGE_BUCKET=my-research-bucket
SCYTHE_STORAGE_BUCKET_PREFIX=scythe

# Timeouts
SCYTHE_TIMEOUT_SCATTER_GATHER_SCHEDULE=10m
SCYTHE_TIMEOUT_SCATTER_GATHER_EXECUTION=20m
SCYTHE_TIMEOUT_EXPERIMENT_SCHEDULE=10m
SCYTHE_TIMEOUT_EXPERIMENT_EXECUTION=5m

# Worker (optional -- defaults are usually fine for local dev)
# SCYTHE_WORKER_DOES_LEAF=True
# SCYTHE_WORKER_DOES_FAN=True
# SCYTHE_WORKER_SLOTS=4
# SCYTHE_WORKER_HAS_GPU=False
```
