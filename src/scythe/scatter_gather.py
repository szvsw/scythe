"""Fanout Handling."""

import tempfile
from functools import cached_property, partial
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

import boto3
import pandas as pd
from hatchet_sdk import Context, TriggerWorkflowOptions
from hatchet_sdk.clients.admin import WorkflowRunTriggerConfig
from pydantic import AnyUrl, BaseModel, Field, field_validator, model_validator

from scythe.base import BaseSpec, ExperimentInputSpec, ExperimentOutputSpec
from scythe.hatchet import hatchet
from scythe.registry import ExperimentRegistry, ExperimentStandaloneType, TOutput
from scythe.storage import ScytheStorageSettings
from scythe.utils.filesys import fetch_uri
from scythe.utils.results import save_and_upload_parquets, transpose_dataframe_dict

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
else:
    S3Client = object


s3 = boto3.client("s3")


class RecursionSpec(BaseModel):
    """A spec for recursive calls."""

    factor: int = Field(..., description="The factor to use in recursive calls", ge=1)
    offset: int | None = Field(
        default=None, description="The offset to use in recursive calls", ge=0
    )

    @model_validator(mode="before")
    @classmethod
    def validate_offset_less_than_factor(cls, values):
        """Validate that the offset is less than the factor."""
        if values["offset"] is None:
            return values
        if values["offset"] >= values["factor"]:
            raise ValueError(f"OFFSET:{values['offset']}>=FACTOR:{values['factor']}")
        return values


class RecursionMap(BaseModel):
    """A map of recursion specs to use in recursive calls.

    This allows a recursion node to understand where
    it is in the recursion tree and how to behave.
    """

    path: list[RecursionSpec] | None = Field(
        default=None, description="The path of recursion specs to use"
    )
    factor: int = Field(..., description="The factor to use in recursive calls", ge=1)
    max_depth: int = Field(
        default=10, description="The maximum depth of the recursion", ge=0, le=10
    )

    @property
    def is_root(self) -> bool:
        """Check if the recursion map is the root."""
        return len(self.path or []) == 0

    @field_validator("path", mode="before")
    @classmethod
    def validate_path_is_length_ge_1(cls, values):
        """Validate that the path is at least length 1."""
        if values is None:
            return values
        if len(values) < 1:
            raise ValueError("PATH:LENGTH:GE:1")
        return values


class GatheredExperimentRuns(BaseModel, arbitrary_types_allowed=True):
    """A class for gathering experiment results."""

    # TODO: make success a little more extensible?
    success: ExperimentOutputSpec
    errors: pd.DataFrame | None


class ScatterGatherInput(BaseSpec):
    """Input for the scatter gather workflow."""

    task_name: str = Field(..., description="The name of the Hatchet task to run.")
    # TODO: consider isolating specs path to allow two versions of the class, including
    # one which takes specs rather than AnyUrl
    specs_path: AnyUrl = Field(..., description="The path to the specs to run.")
    storage_settings: ScytheStorageSettings = Field(
        default_factory=lambda: ScytheStorageSettings(),
        description="The storage settings to use.",
    )
    recursion_map: RecursionMap = Field(..., description="The recursion map to use.")
    save_errors: bool = Field(default=False, description="Whether to save errors.")

    def construct_filekey(
        self,
        filename: str,
        *,
        mode: Literal["input", "output"],
        workflow_run_id: str,
        suffix: str,
    ) -> str:
        """Cosntruct an output key for the scatter gather workflow."""
        bucket_prefix = self.storage_settings.BUCKET_PREFIX
        output_key_base = f"{bucket_prefix}/{self.experiment_id}/{mode}"
        output_results_dir = (
            f"recurse/{len(self.recursion_map.path)}"
            if self.recursion_map.path
            else "root"
        )
        output_key_prefix = f"{output_key_base}/{output_results_dir}"
        return f"{output_key_prefix}/{workflow_run_id}/{filename}.{suffix}"

    @property
    def standalone(self) -> ExperimentStandaloneType:
        """Get the experiment standalone."""
        return ExperimentRegistry.get_experiment(self.task_name)

    @cached_property
    def specs(self) -> list[ExperimentInputSpec]:
        """Fetch the specs and convert to the input type."""
        local_path = self.fetch_uri(self.specs_path, use_cache=True)
        df = pd.read_parquet(local_path)
        specs_dicts = df.to_dict(orient="records")
        validator = self.standalone.input_validator
        return [validator.model_validate(spec) for spec in specs_dicts]

    def add_root_workflow_run_id(self, root_workflow_run_id: str) -> None:
        """Add the root workflow run id to the specs."""
        if self.recursion_map.is_root:
            for spec in self.specs:
                spec.root_workflow_run_id = root_workflow_run_id

    async def run_experiments(
        self,
    ) -> GatheredExperimentRuns:
        """Run the actual experiments and collect results."""
        specs = self.specs
        inputs = [
            self.standalone.create_bulk_run_item(
                input=spec,
                options=TriggerWorkflowOptions(
                    additional_metadata={"index": i},
                ),
            )
            for i, spec in enumerate(specs)
        ]
        # since we don't have a way to get the individual workflow run ids,
        # we can't associate specific results (or errors) with specific results
        results = await self.standalone.aio_run_many(inputs, return_exceptions=True)
        safe_results, error_df = sift_results(specs, results)
        result = combine_experiment_outputs(safe_results)
        return GatheredExperimentRuns(
            success=result,
            errors=error_df,
        )

    def create_recursion_payloads(
        self, parent_workflow_run_id: str
    ) -> tuple[list[WorkflowRunTriggerConfig], list["ScatterGatherInput"]]:
        """Splits up the specs into a list of children scatter gather payloads for recursion."""
        specs = self.specs
        children_payloads: list[ScatterGatherInput] = []
        for branch_ix in range(self.recursion_map.factor):
            new_path = self.recursion_map.path.copy() if self.recursion_map.path else []
            new_path.append(
                RecursionSpec(factor=self.recursion_map.factor, offset=branch_ix)
            )
            recursion_map = RecursionMap(
                path=new_path,
                factor=self.recursion_map.factor,
                max_depth=self.recursion_map.max_depth,
            )
            specs_to_use = specs[branch_ix :: self.recursion_map.factor]
            specs_as_df = pd.DataFrame([
                spec.model_dump(mode="json") for spec in specs_to_use
            ])
            filename = f"specs_{branch_ix:06d}.pq"
            uris = save_and_upload_parquets(
                collected_dfs={
                    filename: specs_as_df,
                },
                s3=s3,
                bucket=self.storage_settings.BUCKET,
                output_key_constructor=partial(
                    self.construct_filekey,
                    mode="input",
                    workflow_run_id=parent_workflow_run_id,
                    suffix="pq",
                ),
            )
            payload = ScatterGatherInput(
                experiment_id=self.experiment_id,
                task_name=self.task_name,
                storage_settings=self.storage_settings,
                specs_path=uris[filename],
                recursion_map=recursion_map,
            )
            del specs_as_df
            del specs_to_use
            children_payloads.append(payload)
        triggers = [
            scatter_gather.create_bulk_run_item(
                input=payload,
                options=TriggerWorkflowOptions(
                    additional_metadata={
                        "index": i,
                        "level": len(self.recursion_map.path or []),
                        "experiment_id": self.experiment_id,
                        "experiment_name": self.task_name,
                    },
                ),
            )
            for i, payload in enumerate(children_payloads)
        ]
        return triggers, children_payloads

    @property
    def is_base_case(self) -> bool:
        """Check if the current payload is a base case, i.e. no recursion needed."""
        too_few_specs = len(self.specs) <= self.recursion_map.factor
        past_max_depth = (
            (len(self.recursion_map.path) >= self.recursion_map.max_depth)
            if self.recursion_map.path
            else False
        ) or self.recursion_map.max_depth == 0
        return too_few_specs or past_max_depth


class ScatterGatherResult(BaseModel):
    """The result of the scatter gather workflow."""

    uris: dict[str, AnyUrl]

    def to_gathered_experiment_runs(self) -> GatheredExperimentRuns:
        """Convert the scatter gather result to a gathered experiment runs."""
        dfs: dict[str, pd.DataFrame] = {}
        for k, v in self.uris.items():
            with tempfile.TemporaryDirectory() as tmpdir:
                f = Path(tmpdir) / "specs.parquet"
                res_path = fetch_uri(uri=v, local_path=f, use_cache=False)
                dfs[k] = pd.read_parquet(res_path)
        return GatheredExperimentRuns(
            success=ExperimentOutputSpec(
                dataframes=dfs,
            ),
            errors=None,
        )


@hatchet.task(name="scatter_gather", input_validator=ScatterGatherInput)
async def scatter_gather(
    payload: ScatterGatherInput,
    ctx: Context,
) -> ScatterGatherResult:
    """Run the scatter gather workflow."""
    payload.add_root_workflow_run_id(ctx.workflow_run_id)
    if payload.is_base_case:
        experiment_output = await payload.run_experiments()
        experiment_outputs = [experiment_output]
    else:
        trigs, children_specs = payload.create_recursion_payloads(ctx.workflow_run_id)
        results = await scatter_gather.aio_run_many(trigs, return_exceptions=True)
        safe_results, error_df = sift_results(children_specs, results)
        experiment_outputs = [r.to_gathered_experiment_runs() for r in safe_results]

    dfs = [r.success.dataframes for r in experiment_outputs]
    errors = [r.errors for r in experiment_outputs if r.errors is not None]
    transposed_dfs = transpose_dataframe_dict(dfs)
    if errors:
        error_dfs = pd.concat(errors, axis=0)
        if "errors" in transposed_dfs:
            transposed_dfs["errors"] = pd.concat(
                [transposed_dfs["errors"], error_dfs], axis=0
            )
        else:
            transposed_dfs["errors"] = error_dfs
    output_key_constructor = partial(
        payload.construct_filekey,
        mode="output",
        workflow_run_id=ctx.workflow_run_id,
        suffix="pq",
    )
    uris = save_and_upload_parquets(
        collected_dfs=transposed_dfs,
        s3=s3,
        bucket=payload.storage_settings.BUCKET,
        output_key_constructor=output_key_constructor,
        save_errors=payload.save_errors,
    )

    return ScatterGatherResult(uris=uris)


ZipDataContent = TypeVar("ZipDataContent", bound=BaseModel)
ResultDataContent = TypeVar("ResultDataContent")


def sift_results(
    spec_data: list[ZipDataContent],
    results: list[ResultDataContent | BaseException],
) -> tuple[list[ResultDataContent], pd.DataFrame | None]:
    """Sift results into safe and errored results.

    Args:
        spec_data (list[ZipDataContent]): The list of spec data.
        results (list[ResultDataContent | BaseException]): The list of results.

    Returns:
        safe_results (list[ResultDataContent]): The list of safe results.
        errors (pd.DataFrame): The DataFrame of errored results.
    """
    safe_results = [r for r in results if not isinstance(r, BaseException)]
    error_specs = [
        spec_data[i] for i, r in enumerate(results) if isinstance(r, BaseException)
    ]

    if error_specs:
        error_msgs = [str(r) for r in results if isinstance(r, BaseException)]
        error_multi_index = pd.MultiIndex.from_frame(
            pd.DataFrame([r.model_dump(mode="json") for r in error_specs])
        )
        error_df = pd.DataFrame(
            {"missing": [False], "msg": error_msgs}, index=error_multi_index
        )
    else:
        error_df = None
    return safe_results, error_df


def combine_experiment_outputs(
    experiment_outputs: list[TOutput],
) -> ExperimentOutputSpec:
    """Combine a list of experiment outputs into a single experiment output."""
    # TODO: handle other keys besides dataframes.
    dataframes = transpose_dataframe_dict([
        output.dataframes for output in experiment_outputs
    ])
    return ExperimentOutputSpec(
        dataframes=dataframes,
    )


if __name__ == "__main__":
    import json

    dataframes = {
        "results": pd.DataFrame({"a": [1, 2, 3]}),
        "metrics": pd.DataFrame({"b": [4, 5, 6]}),
    }
    experiment_output = ExperimentOutputSpec(dataframes=dataframes)
    print(experiment_output.model_dump())
    print(
        experiment_output.model_validate(
            json.loads(experiment_output.model_dump_json())
        )
    )
