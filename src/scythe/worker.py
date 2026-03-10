"""Worker for Scythe."""

import os
from enum import StrEnum

from hatchet_sdk.labels import DesiredWorkerLabel
from hatchet_sdk.runnables.workflow import BaseWorkflow
from pydantic import Field
from pydantic_settings import BaseSettings

from scythe.registry import ExperimentFunction, ExperimentRegistry
from scythe.scatter_gather import scatter_gather


class ScytheWorkerLabel(StrEnum):
    """Label keys used by Scythe workers for task affinity.

    Use these when specifying ``desired_worker_labels`` on experiments so tasks
    are routed to workers with matching capabilities. For example::

    from scythe.worker import ScytheWorkerLabel
    from hatchet_sdk.labels import DesiredWorkerLabel

    ```python
    @ExperimentRegistry.Register(
        desired_worker_labels=ScytheWorkerLabel.HAS_GPU.worker_label
    )
    def my_gpu_experiment(input_spec: MyInput) -> MyOutput:
        ...
    ```

    Or for attaching multiple labels:

    ```python
    @ExperimentRegistry.Register(
        desired_worker_labels={**ScytheWorkerLabel.HAS_GPU.worker_label, **ScytheWorkerLabel.HIGH_MEMORY.worker_label}
    )
    def my_gpu_experiment(input_spec: MyInput) -> MyOutput:
        ...
    ```
    """

    HIGH_MEMORY = "high_memory"
    HIGH_CPU = "high_cpu"
    HAS_GPU = "has_gpu"

    @property
    def worker_label(self) -> dict[str, DesiredWorkerLabel]:
        """Return the worker label."""
        return {self.value: DesiredWorkerLabel(value=self.yes, required=True)}

    @property
    def yes(self) -> str:
        """Return the yes value for the worker label."""
        return "yes"


class WorkerNameConfig(BaseSettings):
    """Configuration for the worker name."""

    FLY_REGION: str | None = None
    AWS_BATCH_JOB_ARRAY_INDEX: int | None = None
    COPILOT_ENVIRONMENT_NAME: str | None = None

    @property
    def in_aws_batch(self) -> bool:
        """Return whether the worker is running in AWS Batch."""
        return self.AWS_BATCH_JOB_ARRAY_INDEX is not None

    @property
    def in_aws_copilot(self) -> bool:
        """Return whether the worker is running in AWS Copilot."""
        return self.COPILOT_ENVIRONMENT_NAME is not None

    @property
    def in_aws(self) -> bool:
        """Return whether the worker is running in AWS."""
        return self.in_aws_batch or self.in_aws_copilot

    @property
    def aws_hosting_str(self):
        """Return the AWS hosting string for the worker."""
        batch = (
            f"Batch{self.AWS_BATCH_JOB_ARRAY_INDEX:04d}" if self.in_aws_batch else ""
        )
        copilot = (
            f"Copilot{(self.COPILOT_ENVIRONMENT_NAME or '').upper()}"
            if self.in_aws_copilot
            else ""
        )
        return f"AWS{batch}{copilot}" if self.in_aws else ""

    @property
    def in_fly(self) -> bool:
        """Return whether the worker is running in Fly.io."""
        return self.FLY_REGION is not None

    @property
    def fly_hosting_str(self):
        """Return the Fly hosting string for the worker."""
        return f"Fly{(self.FLY_REGION or '').upper()}" if self.in_fly else ""

    @property
    def in_local(self) -> bool:
        """Return whether the worker is running locally."""
        return not self.in_aws and not self.in_fly

    @property
    def hosting_str(self):
        """Return the hosting string for the worker."""
        return self.aws_hosting_str or self.fly_hosting_str or "Local"

    @property
    def name(self) -> str:
        """Return the name of the worker."""
        base = "ScytheWorker"
        return f"{base}--{self.hosting_str}"


class ScytheWorkerConfig(BaseSettings, env_prefix="SCYTHE_WORKER_"):
    """Configuration for the Scythe worker."""

    NAME: str | None = Field(default=None, description="The name of the worker.")
    SLOTS: int | None = Field(
        default=None, description="The number of slots the worker has."
    )
    DURABLE_SLOTS: int | None = Field(
        default=None, description="The number of durable slots the worker has."
    )
    HIGH_MEMORY: bool = Field(
        default=False, description="Whether the worker has high memory."
    )
    HIGH_CPU: bool = Field(
        default=False, description="Whether the worker has high CPU."
    )
    HAS_GPU: bool = Field(default=False, description="Whether the worker has a GPU.")

    WORKER_NAME_CONFIG: WorkerNameConfig = Field(
        default_factory=WorkerNameConfig,
        description="The configuration for the worker name.",
    )

    DOES_FAN: bool = True
    DOES_LEAF: bool = True

    @property
    def labels(self) -> dict[str, str | int]:
        """Return the labels for the worker."""
        return {
            label.value: label.yes
            for (label, high) in (
                (ScytheWorkerLabel.HIGH_MEMORY, self.HIGH_MEMORY),
                (ScytheWorkerLabel.HIGH_CPU, self.HIGH_CPU),
                (ScytheWorkerLabel.HAS_GPU, self.HAS_GPU),
            )
            if high
        }

    @property
    def computed_slots(self) -> int:
        """Return the number of slots for the worker."""
        if self.SLOTS is not None:
            return self.SLOTS
        cpu_ct = os.cpu_count() or 1
        if cpu_ct < 8:
            return cpu_ct
        else:
            return cpu_ct - 1

    @property
    def computed_durable_slots(self) -> int:
        """Return the number of durable slots for the worker."""
        if self.DURABLE_SLOTS is not None:
            return self.DURABLE_SLOTS
        return 1000

    @property
    def computed_name(self) -> str:
        """Return the name of the worker."""
        return self.NAME if self.NAME else self.WORKER_NAME_CONFIG.name

    def start(
        self,
        experiments: list[ExperimentFunction] | None = None,
        additional_workflows: list[BaseWorkflow] | None = None,
    ) -> None:
        """Make a worker."""
        from scythe.hatchet import hatchet

        for experiment in experiments or []:
            ExperimentRegistry.Register()(experiment)

        worker = hatchet.worker(
            name=self.computed_name,
            slots=self.computed_slots,
            durable_slots=self.computed_durable_slots,
            labels=self.labels,
        )
        workflows = (
            ([scatter_gather] if self.DOES_FAN else [])
            + (ExperimentRegistry.experiments() if self.DOES_LEAF else [])
            + (additional_workflows or [])
        )
        for workflow in workflows:
            worker.register_workflow(workflow)
        worker.start()
