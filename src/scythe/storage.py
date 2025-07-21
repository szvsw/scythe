"""Storage Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings


class ScytheStorageSettings(BaseSettings, env_prefix="SCYTHE_STORAGE_"):
    """Storage Settings."""

    BUCKET: str = Field(default=..., description="The name of the S3 bucket to use.")
    BUCKET_PREFIX: str = Field(
        default="scythe", description="The prefix to use for the S3 bucket."
    )
