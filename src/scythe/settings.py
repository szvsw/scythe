"""A module for Scythe's settings."""

from datetime import timedelta

from hatchet_sdk.utils.timedelta_to_expression import Duration
from pydantic import Field
from pydantic_settings import BaseSettings


class TimeoutSettings(BaseSettings, env_prefix="SCYTHE_TIMEOUT_"):
    """A class for Scythe's settings."""

    SCATTER_GATHER_SCHEDULE: Duration = Field(
        default=timedelta(hours=1),
        description="The schedule timeout for the scatter gather workflow.",
    )
    SCATTER_GATHER_EXECUTION: Duration = Field(
        default=timedelta(hours=1),
        description="The execution timeout for the scatter gather workflow.",
    )

    EXPERIMENT_SCHEDULE: Duration = Field(
        default=timedelta(hours=1),
        description="The schedule timeout for the simulation workflow.",
    )
    EXPERIMENT_EXECUTION: Duration = Field(
        default=timedelta(minutes=1),
        description="The execution timeout for the simulation workflow.",
    )


timeout_settings = TimeoutSettings()


class ScytheStorageSettings(BaseSettings, env_prefix="SCYTHE_STORAGE_"):
    """Storage Settings."""

    BUCKET: str = Field(default=..., description="The name of the S3 bucket to use.")
    BUCKET_PREFIX: str = Field(
        default="scythe", description="The prefix to use for the S3 bucket."
    )
