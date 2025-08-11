"""Models for Simulation Specifications."""

import importlib
import importlib.resources
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

try:
    # python 3.11+
    from typing import Self  # pyright: ignore [reportAttributeAccessIssue]
except ImportError:
    # python 3.10
    from typing_extensions import Self  # noqa: UP035

import pandas as pd
from pydantic import AnyUrl, BaseModel, Field, field_serializer, field_validator
from pydantic.json_schema import SkipJsonSchema

from scythe.settings import ScytheStorageSettings
from scythe.utils.filesys import FileReference, FileReferenceMixin, S3Url, fetch_uri
from scythe.utils.results import serialize_df_dict

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
else:
    S3Client = object

logger = logging.getLogger(__name__)


# TODO: should experiment ids be uuid trims?
# or should they be human readable (creating unicity issues...)?
# or should they also relate to hatchet auto-generated data?
class BaseSpec(FileReferenceMixin, extra="allow", arbitrary_types_allowed=True):
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

    def _fetch_remote_files_to_cache(self) -> dict[str, Path]:
        """Fetch remote files to cache."""
        remote_artifact_file_paths = self.remote_artifact_file_paths
        local_paths = {
            k: self.fetch_uri(v, use_cache=True)
            for k, v in remote_artifact_file_paths.items()
        }
        return local_paths

    def _fetch_and_replace_file_references(self) -> Self:
        """Fetch remote files to cache and replace file references with local paths."""
        local_paths = self._fetch_remote_files_to_cache()
        new_self = self.model_copy(deep=True)
        for k, v in local_paths.items():
            setattr(new_self, k, v)
        return new_self


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


# TODO: consider making the payload a generic?
class ExperimentInputSpec(BaseSpec):
    """A spec for running a leaf workflow."""

    sort_index: int = Field(..., description="The sort index of the leaf.", ge=0)
    workflow_run_id: str | None = Field(
        default=None, description="The workflow run id of the leaf."
    )
    root_workflow_run_id: str | None = Field(
        default=None, description="The root workflow run id of the leaf."
    )
    storage_settings: ScytheStorageSettings | None = Field(
        default=None, description="The storage settings to use."
    )
    _original_spec: "Self | None" = None

    @property
    def prefix(self) -> str:
        """Get the scoped key for the spec."""
        if self.storage_settings is None:
            msg = "`storage_settings` is not set, so we can't construct a scoped key"
            raise ValueError(msg)
        return f"{self.storage_settings.BUCKET_PREFIX}/{self.experiment_id}"

    @property
    def _index_excluded_fields(self) -> set[str]:
        return {"storage_settings", "_original_spec"}

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

        instance_to_dump = self._original_spec or self
        dumped_index = instance_to_dump.model_dump(
            mode="json", exclude=instance_to_dump._index_excluded_fields
        )
        index_data: list[dict[str, Any]] = [dumped_index for _ in range(n_rows)]

        if isinstance(additional_index_data, dict):
            if any(k in dumped_index for k in additional_index_data):
                overlapping_keys = [
                    k for k in additional_index_data if k in dumped_index
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
            self.log(f"Index data is not serializable: {index_data}")
            raise ExperimentIndexNotSerializableError(self.__class__) from e

        df = pd.DataFrame(index_data)
        if include_sort_subindex and n_rows > 1:
            df["sort_subindex"] = list(range(n_rows))

        return pd.MultiIndex.from_frame(df)

    def construct_output_key(self, field_name: str, fpath: Path) -> str:
        """Construct an output key for a file."""
        sort_str = f"{self.sort_index:08d}"
        fname = f"{self.workflow_run_id or sort_str}{fpath.suffix}"
        base = f"{self.experiment_id}/results/{field_name}/{fname}"
        return base


class ScalarInDataframesError(Exception):
    """An error for when a scalar is in the dataframes."""

    def __init__(self, scalar: Any):
        """Initialize the error."""
        self.scalar = scalar
        super().__init__("`scalars` key is already in `dataframes`")


class ResultFileRefsInDataframesError(Exception):
    """An error for when a result file ref is in the dataframes."""

    def __init__(self, result_file_refs: Any):
        """Initialize the error."""
        self.result_file_refs = result_file_refs
        super().__init__("`result_file_refs` key is already in `dataframes`")


class ExperimentOutputSpec(FileReferenceMixin, arbitrary_types_allowed=True):
    """A spec for the output of a leaf workflow."""

    dataframes: SkipJsonSchema[dict[str, pd.DataFrame]] = Field(default_factory=dict)
    # TODO: consider adding an additional_files key

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

    @property
    def _scalar_excluded_fields(self) -> set[str]:
        """Get the fields to exclude from the scalar data."""
        # TODO: we should also exclude things that aren't really scalars!
        return {"dataframes", *self._file_reference_fields()}

    def _add_scalars(self, input_spec: ExperimentInputSpec):
        """Update the dataframes with the input spec."""
        scalar_data = self.model_dump(mode="json", exclude=self._scalar_excluded_fields)
        if len(scalar_data) == 0:
            return
        results = [scalar_data]
        multi_index = input_spec.make_multiindex(n_rows=1, include_sort_subindex=False)
        df = pd.DataFrame(results, index=multi_index)
        if "scalars" in self.dataframes:
            raise ScalarInDataframesError(self.dataframes["scalars"])
        self.dataframes["scalars"] = df

    def _transfer_files(
        self,
        input_spec: ExperimentInputSpec,
        storage_settings: ScytheStorageSettings | None,
        s3_client: S3Client,
    ):
        """Transfer the files to the output spec."""
        # TODO: consider adding `additional_files` key
        # currently, that would unfortunately require a separate organizational structure
        # in the bucket, since right now we do field/workflow_run_id.suffix,
        # but for additional files, we probably would want to do
        # additional_files/workflow_run_id/{path.name}
        if storage_settings is None:
            input_spec.log("No storage settings provided, skipping file transfer.")
            return
        local_output_artifact_paths = self._local_artifact_file_paths
        non_local_output_artifact_uris = self.remote_artifact_file_paths
        local_output_artifact_destinations = {
            k: f"{storage_settings.BUCKET_PREFIX}/{input_spec.construct_output_key(k, v)}"
            for k, v in local_output_artifact_paths.items()
        }
        # TODO: we could possibly speed this up with a threadpool executor
        for k in local_output_artifact_destinations:
            local_pth = local_output_artifact_paths[k]
            destination_key = local_output_artifact_destinations[k]
            s3_client.upload_file(
                Filename=local_pth.as_posix(),
                Bucket=storage_settings.BUCKET,
                Key=destination_key,
            )

        local_output_artifact_uris = {
            k: S3Url(f"s3://{storage_settings.BUCKET}/{v}")
            for k, v in local_output_artifact_destinations.items()
        }
        all_output_artifact_uris: dict[str, FileReference] = {
            **local_output_artifact_uris,
            **non_local_output_artifact_uris,
        }

        for k, v in local_output_artifact_uris.items():
            setattr(self, k, v)

        # now we want to create a dataframe formatted similarly to scalars
        if len(all_output_artifact_uris) == 0:
            return
        all_output_artifact_uris_as_str = {
            k: str(v) for k, v in all_output_artifact_uris.items()
        }
        results = [all_output_artifact_uris_as_str]
        multi_index = input_spec.make_multiindex(n_rows=1, include_sort_subindex=False)
        df = pd.DataFrame(results, index=multi_index)
        if "result_file_refs" in self.dataframes:
            raise ResultFileRefsInDataframesError(self.dataframes["result_file_refs"])
        self.dataframes["result_file_refs"] = df
