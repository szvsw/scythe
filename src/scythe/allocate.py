"""Allocate an experiment to a workflow run."""

import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
import pandas as pd
import yaml
from hatchet_sdk import TaskRunRef, TriggerWorkflowOptions

from scythe.registry import Standalone, TInput, TOutput
from scythe.scatter_gather import (
    RecursionMap,
    ScatterGatherInput,
    ScatterGatherResult,
    scatter_gather,
)
from scythe.storage import ScytheStorageSettings
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


# TODO: consider factoring this into a an ExperimentRun Class
# which ought to include things like artifact location,
# automatically uploading referenced artifacts, etc.
def allocate_experiment(
    experiment_id: str,
    experiment: Standalone[TInput, TOutput],
    specs: Sequence[TInput],
    recursion_map: RecursionMap | None = None,
    construct_filekey: Callable[[str], str] | None = None,
    storage_settings: ScytheStorageSettings | None = None,
    s3_client: S3Client | None = None,
) -> TaskRunRef[ScatterGatherInput, ScatterGatherResult]:
    """Allocate an experiment to a workflow run."""
    s3_client = s3_client or s3
    storage_settings = storage_settings or ScytheStorageSettings()

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
    for spec in specs:
        spec.experiment_id = experiment_id
    df = pd.DataFrame([s.model_dump(mode="json") for s in specs])
    df_name = "specs"

    def construct_filekey_(filename: str):
        return f"{storage_settings.BUCKET_PREFIX}/{experiment_id}/artifacts/specs/{filename}.pq"

    construct_filekey = construct_filekey or construct_filekey_

    uris = save_and_upload_parquets(
        collected_dfs={df_name: df},
        s3=s3_client,
        bucket=storage_settings.BUCKET,
        output_key_constructor=construct_filekey,
    )
    uri = uris[df_name]
    scatter_gather_input = ScatterGatherInput(
        experiment_id=experiment_id,
        task_name=experiment.name,
        specs_path=uri,
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
    with tempfile.TemporaryDirectory() as temp_dir:
        tdir = Path(temp_dir)
        manifest_path = tdir / "manifest.yml"
        with open(manifest_path, "w") as f:
            yaml.dump(
                {
                    "workflow_run_id": workflow_run_id,
                    "experiment_id": experiment_id,
                    "experiment_name": experiment.name,
                },
                f,
                indent=2,
            )
        file_key = (
            f"{storage_settings.BUCKET_PREFIX}/{experiment_id}/artifacts/manifest.yml"
        )
        s3_client.upload_file(
            Bucket=storage_settings.BUCKET,
            Key=file_key,
            Filename=manifest_path.as_posix(),
        )
    return run_ref
