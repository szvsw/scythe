"""Tests for BaseExperiment.model_copy(deep=True) with non-copyable runnables."""

from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.experiments import BaseExperiment
from scythe.registry import ExperimentRegistry


class _TestModelCopyInput(ExperimentInputSpec):
    """Input spec for model_copy test experiment."""

    a: int


class _TestModelCopyOutput(ExperimentOutputSpec):
    """Output spec for model_copy test experiment."""

    b: str


@ExperimentRegistry.Register(name="test_model_copy_deep_experiment")
def _test_model_copy_experiment(
    input_spec: _TestModelCopyInput,
) -> _TestModelCopyOutput:
    """Minimal experiment for testing model_copy behavior."""
    return _TestModelCopyOutput(b=f"Hello, {input_spec.a}!")


def test_base_experiment_model_copy_deep_preserves_runnable_identity() -> None:
    """Test that model_copy(deep=True) works despite runnables lacking deepcopy support.

    The SerializableRunnable.__deepcopy__ temporarily nulls the runnable before
    delegating to Pydantic's deepcopy, then restores it. This ensures:
    - The copy is a distinct object
    - The runnable is shared (not deep-copied) since runnable types don't implement it
    - Other fields like storage_settings are properly deep-copied
    """
    exp = BaseExperiment(runnable=_test_model_copy_experiment)
    exp2 = exp.model_copy(deep=True)

    assert exp2 is not exp
    assert exp2 == exp

    exp2.run_name = "exp2"

    assert exp2.runnable is exp.runnable
    assert exp2.run_name != exp.run_name
    assert exp2.storage_settings == exp.storage_settings
    assert exp2.storage_settings is not exp.storage_settings
