# Installation

## Prerequisites

- **Python 3.10+** (3.12 recommended)
- **An S3-compatible bucket** for storing experiment specs, artifacts, and results (e.g. AWS S3, MinIO)
- **A Hatchet instance** -- either [Hatchet Cloud](https://cloud.hatchet.run) or [self-hosted](https://docs.hatchet.run/self-hosting)
- **AWS credentials** configured for S3 access (via environment variables, `~/.aws/credentials`, or IAM roles)

!!! tip "Quick start with Docker"
    The [scythe-example](https://github.com/szvsw/scythe-example) repository bundles a local Hatchet instance and S3-compatible storage (LocalStack) via Docker Compose, so you can skip the Hatchet and S3 prerequisites entirely for local development.

## Install Scythe

=== "uv (recommended)"

    ```sh
    uv add scythe-engine
    ```

=== "pip"

    ```sh
    pip install scythe-engine
    ```

=== "poetry"

    ```sh
    poetry add scythe-engine
    ```

The package is published on PyPI as [`scythe-engine`](https://pypi.org/project/scythe-engine).

## Dependencies

Scythe pulls in the following core dependencies automatically:

| Package                          | Purpose                                               |
| -------------------------------- | ----------------------------------------------------- |
| `hatchet-sdk`                    | Distributed task engine client                        |
| `pydantic` / `pydantic-settings` | Schema validation and environment-based configuration |
| `boto3`                          | S3 client for artifact and result storage             |
| `pandas`                         | DataFrame creation and Parquet I/O                    |
| `numpy`                          | Numeric utilities                                     |
| `pyarrow` / `fastparquet`        | Parquet serialization backends                        |
| `pyyaml`                         | Manifest and schema YAML export                       |
| `tqdm`                           | Progress bars during artifact upload                  |

## Environment Variables

At a minimum, you need the following environment variables set before running Scythe:

```sh
# Hatchet connection
HATCHET_CLIENT_TOKEN=<your-hatchet-token>

# S3 storage
SCYTHE_STORAGE_BUCKET=<your-s3-bucket-name>
AWS_REGION=<your-aws-region>
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
```

See the [Configuration Reference](../reference/configuration.md) for the full list of available settings.

## Verify Installation

```python
import scythe
from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.registry import ExperimentRegistry
from scythe.experiments import BaseExperiment

print("Scythe installed successfully!")
```

## Next Steps

Head to the [Quickstart](quickstart.md) to define and run your first experiment.
