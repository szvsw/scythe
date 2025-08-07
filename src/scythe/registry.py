"""Register experiments with Scythe."""

import inspect
import tempfile
from pathlib import Path
from typing import ClassVar, Protocol, TypeVar, cast, get_type_hints

import boto3
from hatchet_sdk import Context, Worker
from hatchet_sdk.labels import DesiredWorkerLabel
from hatchet_sdk.runnables.workflow import Standalone
from hatchet_sdk.utils.timedelta_to_expression import Duration

from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.hatchet import hatchet
from scythe.settings import timeout_settings

ExperimentStandaloneType = Standalone[ExperimentInputSpec, ExperimentOutputSpec]

TInput = TypeVar("TInput", bound=ExperimentInputSpec, contravariant=True)
TOutput = TypeVar("TOutput", bound=ExperimentOutputSpec, covariant=True)


class ExperimentTypeNotFound(Exception):
    """An experiment was not found."""

    def __init__(self, name: str):
        """Initialize the exception."""
        self.name = name
        super().__init__(f"Experiment {name} not found")


class ExperimentTypeExists(Exception):
    """An experiment type already exists."""

    def __init__(self, name: str):
        """Initialize the exception."""
        self.name = name
        super().__init__(f"Experiment {name} already exists")


class ExperimentFunctionWithoutTempdir(Protocol[TInput, TOutput]):
    """A function that can run experiments, with or without tempdir support."""

    def __call__(self, input_spec: TInput) -> TOutput:
        """Invoke the experiment function with flexible signature."""
        ...

    def __name__(self) -> str:
        """The name of the experiment function."""
        ...


class ExperimentFunctionWithTempdir(Protocol[TInput, TOutput]):
    """A function that can run experiments, with tempdir support."""

    def __call__(self, input_spec: TInput, tempdir: Path) -> TOutput:
        """Invoke the experiment function with flexible signature."""
        ...

    def __name__(self) -> str:
        """The name of the experiment function."""
        ...


ExperimentFunction = (
    ExperimentFunctionWithoutTempdir[TInput, TOutput]
    | ExperimentFunctionWithTempdir[TInput, TOutput]
)


def _function_accepts_tempdir(fn_: ExperimentFunction) -> bool:
    """Check if a function accepts a tempdir parameter."""
    sig = inspect.signature(fn_)
    return ("tempdir" in sig.parameters) and (
        sig.parameters["tempdir"].annotation is Path
    )


s3_client = boto3.client("s3")


class ExperimentRegistry:
    """An experiment registry for standalone task steps."""

    _experiments_dict: ClassVar[dict[str, ExperimentStandaloneType]] = {}

    @classmethod
    def Include(
        cls,
        task: Standalone[TInput, TOutput],
    ) -> ExperimentStandaloneType:
        """Register an experiment whose input and output schemas conform to the base types."""
        task_safe = cast(ExperimentStandaloneType, task)
        if task_safe.name in cls._experiments_dict:
            raise ExperimentTypeExists(task_safe.name)
        cls._experiments_dict[task_safe.name] = task_safe
        return task_safe

    @classmethod
    def Register(
        cls,
        *,
        worker: Worker | None = None,
        description: str | None = None,
        name: str | None = None,
        desired_worker_labels: dict[str, DesiredWorkerLabel] | None = None,
        schedule_timeout: Duration = timeout_settings.EXPERIMENT_SCHEDULE,
        execution_timeout: Duration = timeout_settings.EXPERIMENT_EXECUTION,
        retries: int = 1,
        overwrite_log_method: bool = True,
        inject_workflow_run_id: bool = True,
        **task_config,
    ):
        """Decorator to make a standalone experiment from a function.

        Usage:
            @ExperimentRegistry.Register(description="desc", ...)
            def my_experiment(input_spec: MyInput) -> MyOutput:
                ...
        """

        def decorator(
            fn: ExperimentFunction[TInput, TOutput],
        ) -> ExperimentStandaloneType:
            input_type = cast(type[TInput], get_type_hints(fn)["input_spec"])
            return_type = cast(type[TOutput], get_type_hints(fn)["return"])

            fn_name = fn.__name__
            fn_doc = fn.__doc__

            @cls.Include
            @hatchet.task(
                name=name or f"scythe_experiment_{fn_name}",
                description=description or f"{fn_doc}",
                input_validator=input_type,
                desired_worker_labels=desired_worker_labels,
                schedule_timeout=schedule_timeout,
                execution_timeout=execution_timeout,
                retries=retries,
                **task_config,
            )
            def task(input_: input_type, context: Context) -> return_type:  # pyright: ignore [reportInvalidTypeForm]
                """The task implementation."""
                if overwrite_log_method:
                    input_.log = lambda msg: context.log(msg)
                if inject_workflow_run_id:
                    input_.workflow_run_id = context.workflow_run_id
                with tempfile.TemporaryDirectory() as temp_dir:
                    if _function_accepts_tempdir(fn):
                        fn_ = cast(ExperimentFunctionWithTempdir[TInput, TOutput], fn)
                        output = fn_(input_, tempdir=Path(temp_dir))
                    else:
                        fn_ = cast(
                            ExperimentFunctionWithoutTempdir[TInput, TOutput], fn
                        )
                        output = fn_(input_)
                    output._add_scalars(input_)
                    output._transfer_files(
                        input_,
                        input_.storage_settings,
                        s3_client,
                    )
                    return output

            if worker:
                worker.register_workflow(task)
            return task

        return decorator

    @classmethod
    def get_experiment(cls, name: str) -> ExperimentStandaloneType:
        """Get an experiment's Hatchet Stanadalone."""
        if name not in cls._experiments_dict:
            raise ExperimentTypeNotFound(name)
        return cls._experiments_dict[name]

    @classmethod
    def experiments(cls) -> list[ExperimentStandaloneType]:
        """Get all experiments."""
        return list(cls._experiments_dict.values())
