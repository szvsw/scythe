"""Worker for Scythe."""

from pydantic import Field
from pydantic_settings import BaseSettings

from scythe.hatchet import hatchet
from scythe.registry import ExperimentFunction, ExperimentRegistry
from scythe.scatter_gather import scatter_gather


class ScytheWorkerConfig(BaseSettings, env_prefix="SCYTHE_WORKER_"):
    """Configuration for the Scythe worker."""

    name: str = Field(default=..., description="The name of the worker.")
    slots: int = Field(default=..., description="The number of slots the worker has.")
    durable_slots: int = Field(
        default=..., description="The number of durable slots the worker has."
    )
    labels: dict[str, str | int] | None = Field(
        default=None, description="The labels of the worker for affinity purposes."
    )

    def start(self, experiments: list[ExperimentFunction] | None = None) -> None:
        """Make a worker."""
        for experiment in experiments or []:
            ExperimentRegistry.Register(experiment)

        worker = hatchet.worker(
            name=self.name,
            slots=self.slots,
            durable_slots=self.durable_slots,
            labels=self.labels,
            workflows=[
                scatter_gather,
            ],
        )
        for exp in ExperimentRegistry.experiments():
            worker.register_workflow(exp)
        worker.start()
