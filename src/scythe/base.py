"""Models for Simulation Specifications."""

import importlib
import importlib.resources
import logging
from pathlib import Path
from typing import cast

import pandas as pd
from pydantic import AnyUrl, BaseModel, Field, field_serializer, field_validator

from scythe.utils.filesys import fetch_uri
from scythe.utils.results import serialize_df_dict

logger = logging.getLogger(__name__)


# TODO: should experiment ids be uuid trims?
# or should they be human readable (creating unicity issues...)?
# or should they also relate to hatchet auto-generated data?
class BaseSpec(BaseModel, extra="allow", arbitrary_types_allowed=True):
    """A base spec for running a simulation.

    The main features are utilities to fetch files from uris
    and generate a locally scoped path for the files.
    according to the experiment_id.
    """

    experiment_id: str = Field(..., description="The experiment_id of the spec")

    def local_path(self, pth: AnyUrl) -> Path:
        """Return the local path of a uri scoped to the experiment_id.

        Note that this should only be used for non-ephemeral files.

        Args:
            pth (AnyUrl): The uri to convert to a local path

        Returns:
            local_path (Path): The local path of the uri
        """
        path = pth.path

        # get the location of the scythe package
        scythe_dir = importlib.resources.files("scythe")
        # convert the traversable to an absolute path
        scythe_dir = Path(cast(Path, scythe_dir))
        # get the local artifacts directory
        local_artifacts_dir = scythe_dir.parent / "cache"

        if not path or path == "/":
            raise ValueError(f"URI:NO_PATH:{pth}")
        if path.startswith("/"):
            path = path[1:]
        return local_artifacts_dir / self.experiment_id / path

    def log(self, msg: str):
        """Log a message to the context or to the logger.

        Args:
            msg (str): The message to log
        """
        logger.info(msg)

    def fetch_uri(self, uri: AnyUrl, use_cache: bool = True) -> Path:
        """Fetch a file from a uri and return the local path.

        Args:
            uri (AnyUrl): The uri to fetch
            use_cache (bool): Whether to use the cache

        Returns:
            local_path (Path): The local path of the fetched file
        """
        local_path = self.local_path(uri)
        return fetch_uri(uri, local_path, use_cache, self.log)


class ExperimentInputSpec(BaseSpec):
    """A spec for running a leaf workflow."""

    sort_index: int = Field(..., description="The sort index of the leaf.", ge=0)
    workflow_run_id: str | None = Field(
        default=None, description="The workflow run id of the leaf."
    )
    root_workflow_run_id: str | None = Field(
        default=None, description="The root workflow run id of the leaf."
    )


class ExperimentOutputSpec(BaseModel, arbitrary_types_allowed=True):
    """A spec for the output of a leaf workflow."""

    # TODO: make this extensible with scalar columns
    dataframes: dict[str, pd.DataFrame]

    @field_validator("dataframes", mode="before")
    def validate_dataframes(cls, v):
        """Validate the dataframes via deserialization."""
        if isinstance(v, dict):
            v = {
                k: (
                    v
                    if isinstance(v, pd.DataFrame)
                    else pd.DataFrame.from_dict(v, orient="tight")
                )
                for k, v in v.items()
            }
        return v

    @field_serializer("dataframes")
    def serialize_dataframes(self, v):
        """Serialize the dataframes via serialization."""
        return serialize_df_dict(v)
