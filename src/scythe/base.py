"""Models for Simulation Specifications."""

import importlib
import importlib.resources
import json
import logging
from pathlib import Path
from typing import Any, cast

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


class ExperimentIndexNotSerializableError(Exception):
    """An error for when an experiment index is not serializable."""

    def __init__(self, cls: type[BaseModel]):
        """Initialize the error."""
        self.cls = cls
        super().__init__(f"Index data is not serializable as json: {cls.__name__}")


class ExperimentIndexAdditionalDataDoesNotMatchNRowsError(Exception):
    """An error for when the additional index data does not match the number of rows."""

    def __init__(
        self, n_rows: int, additional_index_data: dict[str, Any] | list[dict[str, Any]]
    ):
        """Initialize the error."""
        self.n_rows = n_rows
        self.additional_index_data = additional_index_data
        super().__init__(
            f"Additional index data does not match the number of rows: {n_rows} != {len(additional_index_data)}"
        )


class ExperimentIndexAdditionalDataOverlapsWithSpecError(Exception):
    """An error for when the additional index data overlaps with the spec."""

    def __init__(self, overlapping_keys: list[str]):
        """Initialize the error."""
        self.overlapping_keys = overlapping_keys
        super().__init__(
            f"Additional index data overlaps with the spec: {overlapping_keys}"
        )


class ExperimentInputSpec(BaseSpec):
    """A spec for running a leaf workflow."""

    sort_index: int = Field(..., description="The sort index of the leaf.", ge=0)
    workflow_run_id: str | None = Field(
        default=None, description="The workflow run id of the leaf."
    )
    root_workflow_run_id: str | None = Field(
        default=None, description="The root workflow run id of the leaf."
    )

    def make_multiindex(
        self,
        additional_index_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        n_rows: int = 1,
        include_sort_subindex: bool = True,
    ) -> pd.MultiIndex:
        """Make a MultiIndex from the Spec, and any other methods which might create index data.

        Note that index data should generally be considered as features or inputs, rather than outputs.

        TODO: Feel free to add more args to this method if more values need to be computed.

        Returns:
            multi_index (pd.MultiIndex): The MultiIndex.
        """
        if isinstance(additional_index_data, list) and n_rows != len(
            additional_index_data
        ):
            raise ExperimentIndexAdditionalDataDoesNotMatchNRowsError(
                n_rows, additional_index_data
            )

        index_data: list[dict[str, Any]] = [
            self.model_dump(mode="json") for _ in range(n_rows)
        ]

        if isinstance(additional_index_data, dict):
            if any(k in self.model_dump(mode="json") for k in additional_index_data):
                overlapping_keys = [
                    k
                    for k in additional_index_data
                    if k in self.model_dump(mode="json")
                ]
                raise ExperimentIndexAdditionalDataOverlapsWithSpecError(
                    overlapping_keys
                )
            for d in index_data:
                d.update(additional_index_data)

        elif isinstance(additional_index_data, list):
            for d, ad in zip(index_data, additional_index_data, strict=True):
                if any(k in d for k in ad):
                    overlapping_keys = [k for k in ad if k in d]
                    raise ExperimentIndexAdditionalDataOverlapsWithSpecError(
                        overlapping_keys
                    )
                d.update(ad)

        try:
            json.dumps(index_data)
        except Exception as e:
            raise ExperimentIndexNotSerializableError(self.__class__) from e

        df = pd.DataFrame(index_data)
        if include_sort_subindex and n_rows > 1:
            df["sort_subindex"] = list(range(n_rows))

        return pd.MultiIndex.from_frame(df)


class ScalarInDataframesError(Exception):
    """An error for when a scalar is in the dataframes."""

    def __init__(self, scalar: Any):
        """Initialize the error."""
        self.scalar = scalar
        super().__init__("`scalars` key is already in `dataframes`")


class ExperimentOutputSpec(BaseModel, arbitrary_types_allowed=True):
    """A spec for the output of a leaf workflow."""

    # TODO: make this extensible with scalar columns
    dataframes: dict[str, pd.DataFrame] = Field(default_factory=dict)

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

    def add_scalars(self, input_spec: ExperimentInputSpec):
        """Update the dataframes with the input spec."""
        results = [self.model_dump(mode="json", exclude={"dataframes"})]
        multi_index = input_spec.make_multiindex(
            results, n_rows=1, include_sort_subindex=False
        )
        df = pd.DataFrame(results, index=multi_index)
        if "scalars" in self.dataframes:
            raise ScalarInDataframesError(self.dataframes["scalars"])
        self.dataframes["scalars"] = df
