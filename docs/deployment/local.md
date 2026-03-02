# Local Development

This guide covers running Scythe workers locally using native processes or Docker Compose.

## Prerequisites

- A Hatchet instance -- either [Hatchet Cloud](https://cloud.hatchet.run) or [self-hosted](https://docs.hatchet.run/self-hosting)
- An S3-compatible bucket with configured credentials
- Python 3.10+ with [uv](https://astral.sh/uv) (recommended) or pip

## Environment Setup

Create a `.env` file with the required variables:

```sh title=".env"
# Hatchet
HATCHET_CLIENT_TOKEN=<your-token>

# AWS / S3
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>

# Scythe Storage
SCYTHE_STORAGE_BUCKET=my-research-bucket
SCYTHE_STORAGE_BUCKET_PREFIX=scythe

# Scythe Timeouts
SCYTHE_TIMEOUT_SCATTER_GATHER_SCHEDULE=10m
SCYTHE_TIMEOUT_SCATTER_GATHER_EXECUTION=20m
SCYTHE_TIMEOUT_EXPERIMENT_SCHEDULE=10m
SCYTHE_TIMEOUT_EXPERIMENT_EXECUTION=2m
```

See the [Configuration Reference](../reference/configuration.md) for the complete list.

### Splitting Env Files

For projects with multiple worker roles, it helps to split configuration into separate files:

```sh title=".env.scythe.storage"
SCYTHE_STORAGE_BUCKET=my-research-bucket
SCYTHE_STORAGE_BUCKET_PREFIX=scythe
```

```sh title=".env.scythe.simulations"
SCYTHE_WORKER_DOES_LEAF=True
SCYTHE_WORKER_DOES_FAN=False
SCYTHE_WORKER_SLOTS=1
SCYTHE_TIMEOUT_SCATTER_GATHER_SCHEDULE=10h
SCYTHE_TIMEOUT_SCATTER_GATHER_EXECUTION=10h
SCYTHE_TIMEOUT_EXPERIMENT_SCHEDULE=10h
SCYTHE_TIMEOUT_EXPERIMENT_EXECUTION=30m
```

```sh title=".env.scythe.fanouts"
SCYTHE_WORKER_DOES_LEAF=False
SCYTHE_WORKER_DOES_FAN=True
SCYTHE_WORKER_SLOTS=6
SCYTHE_TIMEOUT_SCATTER_GATHER_SCHEDULE=10h
SCYTHE_TIMEOUT_SCATTER_GATHER_EXECUTION=10h
SCYTHE_TIMEOUT_EXPERIMENT_SCHEDULE=10h
```

Then run workers with multiple env files:

```sh
uv run --env-file .env.aws --env-file .env.hatchet --env-file .env.scythe.storage --env-file .env.scythe.simulations worker
```

## Running Natively

### Single Worker (Both Roles)

```sh
uv run --env-file .env main.py
```

### Separate Leaf and Fan Workers

In separate terminals:

```sh
# Terminal 1: Leaf worker (simulations)
uv run --env-file .env --env-file .env.scythe.simulations main.py

# Terminal 2: Fan worker (scatter/gather)
uv run --env-file .env --env-file .env.scythe.fanouts main.py
```

### Allocating

In a third terminal:

```sh
uv run --env-file .env allocate.py
```

## Using a Makefile

A Makefile simplifies common operations:

```makefile title="Makefile"
.PHONY: install
install:
	@uv sync --all-groups --all-extras

.PHONY: worker
worker:
	@uv run --env-file .env main.py

.PHONY: allocate
allocate:
	@uv run --env-file .env allocate.py
```

Then:

```sh
make install
make worker    # in one terminal
make allocate  # in another terminal
```

## Docker Compose

For containerized local development:

### Dockerfile

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

### Compose File

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

### Running

```sh
docker compose up --build
```

To scale workers:

```sh
docker compose up --build --scale worker=4
```

### Separate Roles

For production-like setups with separate leaf and fan workers:

```yaml title="docker-compose.yml"
services:
  simulations:
    build:
      context: .
      dockerfile: Dockerfile.worker
    env_file:
      - .env
      - .env.scythe.storage
      - .env.scythe.simulations
    deploy:
      replicas: 4

  fanouts:
    build:
      context: .
      dockerfile: Dockerfile.worker
    env_file:
      - .env
      - .env.scythe.storage
      - .env.scythe.fanouts
    deploy:
      replicas: 1
```

## Lab Cluster

If you have access to a set of machines on a local network (e.g. lab desktops), you can run workers on each one. Each machine needs:

1. Network access to your Hatchet instance
2. AWS credentials for S3 access
3. The worker code and dependencies installed

Since Hatchet handles task distribution, you simply start a worker on each machine and they will all pull tasks from the same queue. This is a cost-effective way to run large experiments overnight using idle compute resources.

## Next Steps

- See [Cloud Deployment](cloud.md) for AWS ECS and production infrastructure
- See [Workers](../guides/workers.md) for detailed worker configuration
