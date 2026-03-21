from pathlib import Path
import pandas as pd
import pytest
import os
import sys
import types
sys.modules['scythe.hatchet'] = types.SimpleNamespace(
    hatchet=types.SimpleNamespace(task=lambda *a, **k: (lambda f: f), worker=lambda **k: types.SimpleNamespace(register_workflow=lambda w: None, start=lambda: None))
)
os.environ.setdefault(
    "HATCHET_CLIENT_TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.signature",
)
os.environ.setdefault("HATCHET_CLIENT_SERVER_URL", "http://localhost")
os.environ.setdefault("HATCHET_CLIENT_HOST_PORT", "localhost:1234")
os.environ.setdefault("HATCHET_CLIENT_SUB", "t")
os.environ.setdefault("SCYTHE_STORAGE_BUCKET", "b")

from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.types import S3Url


class MyInput(ExperimentInputSpec):
    a: int
    file: Path


class MyOutput(ExperimentOutputSpec):
    b: int | None = None


def test_recursion_spec_validation():
    from scythe.scatter_gather import RecursionSpec
    RecursionSpec(factor=2, offset=1)
    with pytest.raises(ValueError):
        RecursionSpec(factor=2, offset=2)


def test_recursion_map_properties():
    from scythe.scatter_gather import RecursionMap
    rm = RecursionMap(path=None, factor=2, max_depth=1)
    assert rm.is_root
    with pytest.raises(ValueError):
        RecursionMap(path=[], factor=2, max_depth=1)


def test_construct_filekey_and_base_case(tmp_path):
    from scythe.scatter_gather import RecursionMap, ScatterGatherInput
    spec = MyInput(experiment_id="exp", sort_index=0, file=tmp_path/"f", a=1)
    sgi = ScatterGatherInput(
        experiment_id="exp",
        task_name="task",
        specs_uri=S3Url("s3://b/key"),
        recursion_map=RecursionMap(path=None, factor=2, max_depth=1),
    )
    sgi.__dict__["specs"] = [spec]
    key = sgi.construct_filekey(
        "file",
        mode="input",
        workflow_run_id="wr",
        suffix="pq",
    )
    assert key.endswith("scatter-gather/input/root/wr/file.pq")
    sgi.add_root_workflow_run_id("root")
    assert spec.root_workflow_run_id == "root"
    assert sgi.is_base_case


def test_create_and_combine(monkeypatch, tmp_path):
    from scythe.scatter_gather import (
        ScatterGatherResult,
        combine_experiment_outputs,
    )
    df1 = pd.DataFrame({"x": [1]})
    df2 = pd.DataFrame({"x": [2]})
    out = combine_experiment_outputs([
        ExperimentOutputSpec(dataframes={"d": df1}),
        ExperimentOutputSpec(dataframes={"d": df2}),
    ])
    assert out.dataframes["d"].shape == (2, 1)

    class DummyResponse:
        pass

    tmp_file = tmp_path / "res.pq"
    df1.to_parquet(tmp_file)
    monkeypatch.setattr(
        "scythe.scatter_gather.fetch_uri", lambda uri, local_path, use_cache: tmp_file
    )
    res = ScatterGatherResult(uris={"d": S3Url("s3://b/k")})
    gathered = res.to_gathered_experiment_runs()
    assert "d" in gathered.success.dataframes


def test_sift_results():
    from scythe.scatter_gather import sift_results
    class Spec(ExperimentInputSpec):
        a: int
        file: Path

    s1 = Spec(experiment_id="e", sort_index=0, file=Path("f1"), a=1)
    s2 = Spec(experiment_id="e", sort_index=1, file=Path("f2"), a=2)
    safe, errors = sift_results([s1, s2], [1, ValueError("bad")])
    assert safe == [1]
    assert "bad" in errors["msg"].iloc[0]


def test_additional_construct_and_errors(tmp_path):
    from scythe.scatter_gather import ScatterGatherInput, RecursionMap, RecursionSpec
    spec = MyInput(experiment_id="exp", sort_index=0, file=tmp_path/"f", a=1)
    rm = RecursionMap(path=[RecursionSpec(factor=2, offset=0)], factor=2, max_depth=1)
    sgi = ScatterGatherInput(
        experiment_id="exp",
        task_name="task",
        specs_uri=S3Url("s3://b/k"),
        recursion_map=rm,
    )
    sgi.__dict__["specs"] = [spec, spec]
    key = sgi.construct_filekey("x", mode="final", workflow_run_id="wr", suffix="pq")
    assert "final" in key
    assert not sgi.is_root
    assert sgi.is_base_case

def test_sift_results_errors():
    from scythe.scatter_gather import sift_results
    from .test_registry_and_scatter import Out
    class Spec(ExperimentInputSpec):
        a: int
        file: Path
    s1 = Spec(experiment_id="e", sort_index=0, file=Path("f1"), a=1)
    s2 = Spec(experiment_id="e", sort_index=1, file=Path("f2"), a=2)
    safe, err = sift_results([s1, s2], [ValueError("bad"), Out()])
    assert len(safe) == 1 and err is not None
