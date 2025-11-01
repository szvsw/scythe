from __future__ import annotations

import asyncio
import types
from pathlib import Path

import pandas as pd
import pytest

from scythe.base import ExperimentInputSpec, ExperimentOutputSpec
from scythe.types import S3Url, FileReference


class Inp(ExperimentInputSpec):
    val: int
    file: FileReference


class Out(ExperimentOutputSpec):
    num: int | None = None


def test_fetch_uri_edge_cases(monkeypatch, tmp_path):
    from scythe.utils.filesys import fetch_uri

    dest = tmp_path / "f.txt"
    # S3 missing bucket
    with pytest.raises(ValueError):
        fetch_uri("s3:///foo", dest, use_cache=False)

    # http skip when cached
    class DummyResp:
        def __init__(self, content):
            self.content = content
    monkeypatch.setattr("requests.get", lambda url, timeout: DummyResp(b"h"))
    fetch_uri("http://x", dest, use_cache=False)
    before = dest.read_bytes()
    fetch_uri("http://x", dest, use_cache=True)
    assert dest.read_bytes() == before

    # file scheme with missing path
    class DummyFile:
        scheme = "file"
        path = ""
    with pytest.raises(ValueError):
        fetch_uri(DummyFile(), dest, use_cache=False)
    # s3 skip when cached
    class DummyS3:
        def __init__(self):
            self.downloaded = []
        def download_file(self, bucket, key, filename):
            self.downloaded.append((bucket, key, filename))
    ds = DummyS3()
    monkeypatch.setattr("scythe.utils.filesys.s3", ds)
    uri = S3Url("s3://bucket/foo")
    fetch_uri(uri, dest, use_cache=False, s3=ds)
    first = dest.read_bytes()
    fetch_uri(uri, dest, use_cache=True, s3=ds)
    assert dest.read_bytes() == first
    assert len(ds.downloaded) == 1

def test_save_and_upload_parquets_skip(monkeypatch, tmp_path):
    from scythe.utils.results import save_and_upload_parquets

    class DummyS3:
        def __init__(self):
            self.uploaded = []
        def upload_file(self, Bucket, Key, Filename):
            self.uploaded.append((Bucket, Key))
    ds = DummyS3()
    df = pd.DataFrame({"a": [1]})
    uris = save_and_upload_parquets(
        {"error_result": df, "ok": df},
        ds,
        "b",
        lambda n: f"{n}.pq",
        save_errors=False,
    )
    assert "ok" in uris and "error_result" not in uris
    assert ("b", "ok.pq") in ds.uploaded

def test_register_decorator_exec(monkeypatch):
    from scythe import registry as reg

    reg.ExperimentRegistry._experiments_dict.clear()
    monkeypatch.setattr(reg.ExperimentRegistry, "Include", classmethod(lambda cls, t: t))

    def dummy_task(**kw):
        def deco(fn):
            fn.decorated_name = kw.get("name")
            return fn
        return deco
    monkeypatch.setattr(reg, "hatchet", types.SimpleNamespace(task=dummy_task))

    @reg.ExperimentRegistry.Register()
    def fn(input_spec: Inp) -> Out:
        return Out(num=1)

    ctx = types.SimpleNamespace(log=lambda m: None, workflow_run_id="wr")
    spec = Inp(experiment_id="e", sort_index=0, val=5, file=Path("/tmp/x"))
    out = fn(spec, ctx)
    assert spec.workflow_run_id == "wr"
    assert hasattr(out, "dataframes") and "scalars" in out.dataframes

def test_scatter_gather_base_case(monkeypatch, tmp_path):
    from scythe.scatter_gather import ScatterGatherInput, RecursionMap, scatter_gather, GatheredExperimentRuns

    df = pd.DataFrame({"x": [1]})
    async def fake_run_experiments(self):
        return GatheredExperimentRuns(success=ExperimentOutputSpec(dataframes={"d": df}), errors=None)
    monkeypatch.setattr(ScatterGatherInput, "run_experiments", fake_run_experiments)

    monkeypatch.setattr("scythe.scatter_gather.save_and_upload_parquets", lambda collected_dfs, **k: {kname: S3Url(f"s3://b/{kname}") for kname in collected_dfs})
    monkeypatch.setattr("scythe.scatter_gather.fetch_uri", lambda uri, local_path, use_cache: tmp_path)

    spec = Inp(experiment_id="e", sort_index=0, val=1, file=tmp_path/"f")
    rm = RecursionMap(path=None, factor=2, max_depth=1)
    sgi = ScatterGatherInput(experiment_id="e", task_name="t", specs_uri=S3Url("s3://b/k"), recursion_map=rm)
    sgi.__dict__["specs"] = [spec]
    ctx = types.SimpleNamespace(workflow_run_id="wr")
    res = asyncio.run(scatter_gather(sgi, ctx))
    assert "d" in res.uris

def test_scatter_gather_recursive(monkeypatch, tmp_path):
    from scythe.scatter_gather import ScatterGatherInput, RecursionMap, scatter_gather

    async def fake_aio_run_many(trigs, return_exceptions=True):
        class Dummy:
            def to_gathered_experiment_runs(self):
                return types.SimpleNamespace(success=ExperimentOutputSpec(dataframes={"d": pd.DataFrame({"x": [2]})}), errors=None)
        return [Dummy()]
    import scythe.scatter_gather as sg_mod
    monkeypatch.setattr(sg_mod.scatter_gather, "aio_run_many", fake_aio_run_many, raising=False)

    def fake_create(self, wr):
        return ["trig"], [types.SimpleNamespace(model_dump=lambda mode='json': {"v": 1})]
    monkeypatch.setattr(ScatterGatherInput, "create_recursion_payloads", fake_create)
    monkeypatch.setattr("scythe.scatter_gather.save_and_upload_parquets", lambda collected_dfs, **k: {kname: S3Url(f"s3://b/{kname}") for kname in collected_dfs})
    monkeypatch.setattr("scythe.scatter_gather.fetch_uri", lambda uri, local_path, use_cache: tmp_path)

    spec = Inp(experiment_id="e", sort_index=0, val=1, file=tmp_path/"f")
    rm = RecursionMap(path=None, factor=1, max_depth=2)
    sgi = ScatterGatherInput(experiment_id="e", task_name="t", specs_uri=S3Url("s3://b/k"), recursion_map=rm)
    sgi.__dict__["specs"] = [spec, spec]
    ctx = types.SimpleNamespace(workflow_run_id="wr")
    res = asyncio.run(scatter_gather(sgi, ctx))
    assert "d" in res.uris

def test_allocate_experiment_errors(monkeypatch, tmp_path):
    from scythe.allocate import allocate_experiment, DuplicateInputArtifactsError
    class DummyExp:
        name = "d"
        config = type("cfg", (), {"input_validator": Inp})
        input_validator = Inp
        _output_validator = Out
    f = tmp_path/"dir1"/"x.txt"
    f.parent.mkdir()
    f.write_text("x")
    f2 = tmp_path/"dir2"/"x.txt"
    f2.parent.mkdir()
    f2.write_text("y")
    spec1 = Inp(experiment_id="e", sort_index=0, val=1, file=f)
    spec2 = Inp(experiment_id="e", sort_index=1, val=2, file=f2)
    with pytest.raises(DuplicateInputArtifactsError):
        allocate_experiment("e", DummyExp(), [spec1, spec2], s3_client=types.SimpleNamespace(upload_file=lambda **k: None))

    DummyExp._output_validator = None  # type: ignore[assignment]
    monkeypatch.setattr(
        "scythe.allocate.save_and_upload_parquets",
        lambda collected_dfs, **k: {n: S3Url(f"s3://b/{n}") for n in collected_dfs},
    )
    monkeypatch.setattr(
        "scythe.allocate.scatter_gather",
        types.SimpleNamespace(run_no_wait=lambda *a, **k: types.SimpleNamespace(workflow_run_id="wr")),
    )
    monkeypatch.setattr(
        "scythe.allocate.upload_input_artifacts",
        lambda arts, *a, **k: (
            types.SimpleNamespace(files={"file": {S3Url("s3://b/art")}}),
            {"file": {next(iter(arts["file"])): S3Url("s3://b/art")}},
        ),
    )
    with pytest.raises(ValueError):
        allocate_experiment("e", DummyExp(), [spec1], s3_client=types.SimpleNamespace(upload_file=lambda **k: None))

def test_scatter_gather_main(monkeypatch):
    import runpy, builtins
    recorded = []
    monkeypatch.setattr(builtins, "print", lambda *a, **k: recorded.append(a))
    runpy.run_module("scythe.scatter_gather", run_name="__main__")
    assert recorded
