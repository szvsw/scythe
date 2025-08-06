"""Allocate an experiment to a workflow run."""

import tempfile
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import boto3
import pandas as pd
import yaml
from hatchet_sdk import TaskRunRef, TriggerWorkflowOptions
from pydantic import BaseModel, Field, FilePath
from tqdm import tqdm

from scythe.registry import Standalone, TInput, TOutput
from scythe.scatter_gather import (
    RecursionMap,
    ScatterGatherInput,
    ScatterGatherResult,
    scatter_gather,
)
from scythe.settings import ScytheStorageSettings
from scythe.types import S3Url
from scythe.utils.results import save_and_upload_parquets

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
else:
    S3Client = object

s3 = boto3.client("s3")


class ExperimentSpecsMismatchError(Exception):
    """An error raised when the specs for an experiment do not match the expected type."""

    def __init__(self, expected_type: type, actual_type: type):
        """Initialize the error."""
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(
            f"Expected type {expected_type.__name__}, got {actual_type.__name__}."
        )


class DuplicateInputArtifactsError(Exception):
    """An error raised when a file is duplicated in the input artifacts."""

    def __init__(self, file_name: str, field_name: str):
        """Initialize the error."""
        self.file_name = file_name
        self.field_name = field_name
        super().__init__(
            f"File with name {file_name} for field {field_name} is duplicated in the "
            f"input artifacts (i.e. multiple files with the same name but in different "
            "directories.) "
        )


class InputArtifactLocations(BaseModel):
    """The locations of the input artifacts for an experiment."""

    files: dict[str, set[S3Url]]


class ExperimentRunManifest(BaseModel):
    """The manifest for an experiment run."""

    workflow_run_id: str
    experiment_id: str
    experiment_name: str
    specs_uri: S3Url
    io_spec: S3Url
    input_artifacts: S3Url | None = None


class SemVer(BaseModel):
    """A semantic version."""

    major: int
    minor: int = 0
    patch: int = 0

    @classmethod
    def FromString(cls, version: str) -> "SemVer":
        """Parse a semantic version from a string."""
        if not version.startswith("v"):
            msg = "Version must start with 'v'"
            raise ValueError(msg)
        version = version[1:]
        delimiter = "." if "." in version else "-"
        parts = version.split(delimiter)
        if len(parts) == 0:
            msg = "Version must have at least one part"
            raise ValueError(msg)
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return cls(major=major, minor=minor, patch=patch)

    def __lt__(self, other: "SemVer") -> bool:
        """Compare two semantic versions."""
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        return self.patch < other.patch

    def __le__(self, other: "SemVer") -> bool:
        """Compare two semantic versions."""
        if self.major != other.major:
            return self.major <= other.major
        if self.minor != other.minor:
            return self.minor <= other.minor
        return self.patch <= other.patch

    def __gt__(self, other: "SemVer") -> bool:
        """Compare two semantic versions."""
        if self.major != other.major:
            return self.major > other.major
        if self.minor != other.minor:
            return self.minor > other.minor
        return self.patch > other.patch

    def __ge__(self, other: "SemVer") -> bool:
        """Compare two semantic versions."""
        if self.major != other.major:
            return self.major >= other.major
        if self.minor != other.minor:
            return self.minor >= other.minor
        return self.patch >= other.patch

    def next_major_version(self) -> "SemVer":
        """Get the next major version."""
        return SemVer(major=self.major + 1, minor=0, patch=0)

    def next_minor_version(self) -> "SemVer":
        """Get the next minor version."""
        return SemVer(major=self.major, minor=self.minor + 1, patch=0)

    def next_patch_version(self) -> "SemVer":
        """Get the next patch version."""
        return SemVer(major=self.major, minor=self.minor, patch=self.patch + 1)

    def __str__(self) -> str:
        """Get the string representation of the semantic version."""
        return f"v{self.major}.{self.minor}.{self.patch}"


# TODO: consider factoring this into a an ExperimentRun Class
# which ought to include things like artifact location,
# automatically uploading referenced artifacts, etc.
def allocate_experiment(  # noqa: C901
    experiment: Standalone[TInput, TOutput],
    specs: Sequence[TInput],
    experiment_id: str | None = None,
    version: SemVer
    | Literal["bumpmajor", "bumpminor", "bumppatch", "keep"] = "bumpmajor",
    overwrite_sort_index: bool = True,
    overwrite_experiment_id: bool = True,
    recursion_map: RecursionMap | None = None,
    construct_specs_filekey: Callable[[str], str] | None = None,
    storage_settings: ScytheStorageSettings | None = None,
    s3_client: S3Client | None = None,
) -> TaskRunRef[ScatterGatherInput, ScatterGatherResult]:
    """Allocate an experiment to a workflow run."""
    s3_client = s3_client or s3
    storage_settings = storage_settings or ScytheStorageSettings()
    experiment_id = experiment_id or experiment.name
    if not isinstance(version, SemVer):
        prefix = f"{storage_settings.BUCKET_PREFIX}/{experiment_id}/"
        # check s3 for any existing versions of the experiment by listing everything with
        # the prefix
        version_response = s3_client.list_objects_v2(
            Bucket=storage_settings.BUCKET, Prefix=prefix, Delimiter="/"
        )
        # get all of the unique version strings by removing the prefix and grabbing everything
        common_prefixes = version_response.get("CommonPrefixes", [])
        prefixes = [d.get("Prefix", None) for d in common_prefixes]
        prefixes = [p.split("/")[-2] for p in prefixes if p is not None]
        versions = [SemVer.FromString(p) for p in prefixes]
        highest_version = max(versions) if versions else None
        version = (
            (
                highest_version.next_patch_version()
                if version == "bumppatch"
                else highest_version.next_minor_version()
                if version == "bumpminor"
                else highest_version.next_major_version()
                if version == "bumpmajor"
                else highest_version
            )
            if highest_version
            else SemVer(major=1, minor=0, patch=0)
        )
    datetimestr = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    experiment_id = f"{experiment_id}/{version}/{datetimestr}"
    mismatching_types = [
        type(spec)
        for spec in specs
        if not isinstance(spec, experiment.config.input_validator)
    ]
    if mismatching_types:
        raise ExperimentSpecsMismatchError(
            expected_type=experiment.config.input_validator,
            actual_type=mismatching_types[0],
        )
    for i, spec in enumerate(specs):
        if overwrite_experiment_id:
            spec.experiment_id = experiment_id
        if overwrite_sort_index:
            spec.sort_index = i

    # handle local file transfer to s3
    # TODO: this will cause a race condition if multile files have the same name but
    # live in different directories.
    # hence the checks below
    def construct_input_artifact_key(pth: FilePath, field_name: str):
        return f"{storage_settings.BUCKET_PREFIX}/{experiment_id}/artifacts/{field_name}/{pth.name}"

    local_input_artifact_paths = [
        spec._local_input_artifact_file_paths for spec in specs
    ]
    input_artifacts: dict[str, set[FilePath]] = {}
    at_least_one_input_artifact = False
    for spec_paths in local_input_artifact_paths:
        for field_name, fpath in spec_paths.items():
            input_artifacts.setdefault(field_name, set()).add(fpath)
            at_least_one_input_artifact = True

    all_input_artifact_names: dict[str, set[str]] = {}
    for field_name, fpaths in input_artifacts.items():
        for fpath in fpaths:
            file_key = construct_input_artifact_key(fpath, field_name)
            if file_key in all_input_artifact_names.get(field_name, set()):
                raise DuplicateInputArtifactsError(file_key, field_name)
            all_input_artifact_names.setdefault(field_name, set()).add(file_key)

    input_artifacts_s3_urls = None
    if at_least_one_input_artifact:
        input_artifacts_s3_urls, input_artifacts_s3_url_maps = upload_input_artifacts(
            input_artifacts,
            s3_client,
            storage_settings.BUCKET,
            construct_input_artifact_key,
        )
        for spec in specs:
            for field_name, fpath in spec._local_input_artifact_file_paths.items():
                uri_map = input_artifacts_s3_url_maps[field_name]
                uri = uri_map[fpath]
                setattr(spec, field_name, uri)

    df = pd.DataFrame([s.model_dump(mode="json") for s in specs])
    df_name = "specs"

    def construct_specs_filekey_(filename: str):
        return f"{storage_settings.BUCKET_PREFIX}/{experiment_id}/{filename}.pq"

    construct_specs_filekey = construct_specs_filekey or construct_specs_filekey_

    uris = save_and_upload_parquets(
        collected_dfs={df_name: df},
        s3=s3_client,
        bucket=storage_settings.BUCKET,
        output_key_constructor=construct_specs_filekey,
    )
    specs_uri = uris[df_name]
    scatter_gather_input = ScatterGatherInput(
        experiment_id=experiment_id,
        task_name=experiment.name,
        specs_uri=specs_uri,
        recursion_map=recursion_map or RecursionMap(path=None, factor=10, max_depth=0),
        storage_settings=storage_settings,
    )

    run_ref = scatter_gather.run_no_wait(
        scatter_gather_input,
        options=TriggerWorkflowOptions(
            additional_metadata={
                "experiment_id": experiment_id,
                "experiment_name": experiment.name,
                "level": 0,
            }
        ),
    )
    workflow_run_id = run_ref.workflow_run_id

    input_validator = experiment.input_validator
    output_validator = experiment._output_validator
    if output_validator is None:
        msg = "Output validator is not set for experiment"
        raise ValueError(msg)

    class ExperimentIO(BaseModel):
        """The input and output schema for the experiment."""

        input: input_validator = Field(  # pyright: ignore [reportInvalidTypeForm]
            default=..., description="The input for the experiment."
        )
        output: output_validator = Field(  # pyright: ignore [reportInvalidTypeForm]
            default=..., description="The output for the experiment."
        )

    schema = ExperimentIO.model_json_schema()

    with tempfile.TemporaryDirectory() as temp_dir:
        tdir = Path(temp_dir)
        manifest_path = tdir / "manifest.yml"
        io_path = tdir / "experiment_io_spec.yml"
        input_artifacts_path = tdir / "input_artifacts.yml"

        # dump and upload the schema
        with open(io_path, "w") as f:
            yaml.dump(schema, f, indent=2)
        io_file_key = (
            f"{storage_settings.BUCKET_PREFIX}/{experiment_id}/experiment_io_spec.yml"
        )
        s3_client.upload_file(
            Bucket=storage_settings.BUCKET,
            Key=io_file_key,
            Filename=io_path.as_posix(),
        )

        # dump and upload the source files
        s3_input_artifacts_key = (
            f"{storage_settings.BUCKET_PREFIX}/{experiment_id}/input_artifacts.yml"
        )
        if input_artifacts_s3_urls:
            with open(input_artifacts_path, "w") as f:
                yaml.dump(
                    input_artifacts_s3_urls.model_dump(mode="json"),
                    f,
                    indent=2,
                )
            s3_client.upload_file(
                Bucket=storage_settings.BUCKET,
                Key=s3_input_artifacts_key,
                Filename=input_artifacts_path.as_posix(),
            )

        manifest_file_key = (
            f"{storage_settings.BUCKET_PREFIX}/{experiment_id}/manifest.yml"
        )
        io_spec_uri = S3Url(f"s3://{storage_settings.BUCKET}/{io_file_key}")
        input_artifacts_uri = S3Url(
            f"s3://{storage_settings.BUCKET}/{s3_input_artifacts_key}"
        )
        manifest = ExperimentRunManifest(
            workflow_run_id=workflow_run_id,
            experiment_id=experiment_id,
            experiment_name=experiment.name,
            io_spec=io_spec_uri,
            input_artifacts=input_artifacts_uri,
            specs_uri=specs_uri,
        )
        with open(manifest_path, "w") as f:
            yaml.dump(manifest.model_dump(mode="json"), f, indent=2)
        s3_client.upload_file(
            Bucket=storage_settings.BUCKET,
            Key=manifest_file_key,
            Filename=manifest_path.as_posix(),
        )

    return run_ref


def upload_input_artifacts(
    input_artifacts: dict[str, set[FilePath]],
    s3_client: S3Client,
    bucket: str,
    construct_artifact_key: Callable[[FilePath, str], str],
) -> tuple[InputArtifactLocations, dict[str, dict[FilePath, S3Url]]]:
    """Upload source files to S3."""

    def handle_path(pth: FilePath, field_name: str):
        filekey = construct_artifact_key(pth, field_name)
        uri = S3Url(f"s3://{bucket}/{filekey}")
        s3_client.upload_file(
            Bucket=bucket,
            Key=filekey,
            Filename=pth.as_posix(),
        )
        return field_name, uri

    args: list[tuple[FilePath, str]] = []
    for field_name, paths in input_artifacts.items():
        for pth in paths:
            args.append((pth, field_name))
    with ThreadPoolExecutor(max_workers=10) as executor:
        first_args = [a[0] for a in args]
        second_args = [a[1] for a in args]
        results = list(
            tqdm(
                executor.map(handle_path, first_args, second_args),
                total=len(args),
                desc="Uploading source files",
            )
        )
    uris: dict[str, set[S3Url]] = {}
    for field_name, uri in results:
        uris.setdefault(field_name, set()).add(uri)
    uri_maps: dict[str, dict[FilePath, S3Url]] = {}
    for (field_name, uri), (pth, _) in zip(results, args, strict=True):
        uri_maps.setdefault(field_name, {})[pth] = uri
    return InputArtifactLocations(files=uris), uri_maps
