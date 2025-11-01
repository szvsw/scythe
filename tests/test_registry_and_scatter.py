import os
import sys
import types
import pandas as pd
import pytest
import asyncio

def dummy_task(**kw):
    def deco(fn):
        fn.name = kw.get("name", fn.__name__)
        return fn
    return deco

dummy_worker = types.SimpleNamespace(register_workflow=lambda w: None, start=lambda: None)
sys.modules['scythe.hatchet'] = types.SimpleNamespace(
    hatchet=types.SimpleNamespace(task=dummy_task, worker=lambda **k: dummy_worker)
)
os.environ.setdefault("SCYTHE_STORAGE_BUCKET", "b")

from pathlib import Path
from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.types import S3Url

class Inp(ExperimentInputSpec):
    val: int

class Out(ExperimentOutputSpec):
    pass


def test_registry_include_and_get():
    from scythe.registry import ExperimentRegistry, ExperimentTypeExists, ExperimentTypeNotFound
    ExperimentRegistry._experiments_dict.clear()
    dummy = types.SimpleNamespace(name="foo", config=None)
    out = ExperimentRegistry.Include(dummy)
    assert ExperimentRegistry.get_experiment("foo") is dummy
    with pytest.raises(ExperimentTypeExists):
        ExperimentRegistry.Include(dummy)
    with pytest.raises(ExperimentTypeNotFound):
        ExperimentRegistry.get_experiment("bar")


def test_register_decorator():
    from scythe.registry import ExperimentRegistry
    ExperimentRegistry._experiments_dict.clear()
    monkeypatch_include = lambda task: task
    ExperimentRegistry.Include = classmethod(lambda cls, t: monkeypatch_include(t))

    @ExperimentRegistry.Register()
    def fn(input_spec: Inp) -> Out:
        return Out()

    assert callable(fn)


def test_run_experiments(monkeypatch, tmp_path):
    from scythe.scatter_gather import ScatterGatherInput, RecursionMap
    from scythe.registry import ExperimentRegistry

    class Standalone:
        def create_bulk_run_item(self, input, options):
            return input
        async def aio_run_many(self, inputs, return_exceptions=True):
            return [Out(dataframes={"d": pd.DataFrame({"x": [i]})}) for i,_ in enumerate(inputs)]

    spec = Inp(experiment_id="e", sort_index=0, val=1)
    sgi = ScatterGatherInput(
        experiment_id="e",
        task_name="task",
        specs_uri=S3Url("s3://b/k"),
        recursion_map=RecursionMap(path=None, factor=2, max_depth=1),
    )
    sgi.__dict__["specs"] = [spec, spec]
    monkeypatch.setattr(ExperimentRegistry, "get_experiment", lambda name: Standalone())
    result = asyncio.run(sgi.run_experiments())
    assert result.success.dataframes["d"].shape[0] == 2


def test_create_recursion_payloads(monkeypatch, tmp_path):
    from scythe.scatter_gather import ScatterGatherInput, RecursionMap
    import scythe.scatter_gather as sg_mod

    spec = Inp(experiment_id="e", sort_index=0, val=1)
    sgi = ScatterGatherInput(
        experiment_id="e",
        task_name="task",
        specs_uri=S3Url("s3://b/k"),
        recursion_map=RecursionMap(path=None, factor=2, max_depth=2),
    )
    sgi.__dict__["specs"] = [spec, spec, spec, spec]
    monkeypatch.setattr(
        sg_mod,
        "save_and_upload_parquets",
        lambda collected_dfs, *a, **k: {kname: S3Url(f"s3://b/{kname}") for kname in collected_dfs},
    )
    monkeypatch.setattr(sg_mod, "scatter_gather", types.SimpleNamespace(create_bulk_run_item=lambda input, options: (input, options)))
    trigs, payloads = sgi.create_recursion_payloads("wr")
    assert len(payloads) == 2
    assert trigs[0][1].additional_metadata["level"] == 0

