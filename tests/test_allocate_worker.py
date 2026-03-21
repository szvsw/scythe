import os
import sys
import types
from pathlib import Path
import pandas as pd
import pytest
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


from scythe.types import FileReference


class MyInput(ExperimentInputSpec):
    a: int
    file: FileReference


class MyOutput(ExperimentOutputSpec):
    b: int | None = None


class DummyS3:
    def __init__(self):
        self.uploaded: list[tuple[str, str, str]] = []

    def upload_file(self, Bucket: str, Key: str, Filename: str) -> None:
        self.uploaded.append((Bucket, Key, Filename))


def test_upload_input_artifacts(tmp_path):
    from scythe.allocate import upload_input_artifacts
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    f2 = tmp_path / "b.txt"
    f2.write_text("y")
    artifacts = {"file": {f1, f2}}
    ds = DummyS3()

    def key_builder(p: Path, field: str) -> str:
        return f"prefix/{field}/{p.name}"

    locs, maps = upload_input_artifacts(artifacts, ds, "bucket", key_builder)
    assert locs.files["file"]
    assert maps["file"][f1].path.endswith("a.txt")
    assert ("bucket", "prefix/file/a.txt", f1.as_posix()) in ds.uploaded



def test_allocate_experiment_basic(monkeypatch, tmp_path):
    from scythe.allocate import (
        allocate_experiment,
        InputArtifactLocations,
    )
    from scythe.types import S3Url
    class DummyExp:
        name = "dummy"
        config = type("cfg", (), {"input_validator": MyInput})
        input_validator = MyInput
        _output_validator = MyOutput

    ds = DummyS3()

    def fake_run_no_wait(payload, options):
        class R:
            workflow_run_id = "wr"
        return R()

    monkeypatch.setattr("scythe.allocate.scatter_gather", type("SG", (), {"run_no_wait": staticmethod(fake_run_no_wait)}))

    def fake_upload_input_artifacts(arts, s3_client, bucket, key_fn):
        maps = {f: {p: S3Url(f"s3://{bucket}/{key_fn(p,f)}") for p in ps} for f, ps in arts.items()}
        locs = InputArtifactLocations(files={f: set(u for u in m.values()) for f, m in maps.items()})
        return locs, maps

    monkeypatch.setattr("scythe.allocate.upload_input_artifacts", fake_upload_input_artifacts)

    tmp_file = tmp_path / "f.txt"
    tmp_file.write_text("hi")
    spec = MyInput(experiment_id="", sort_index=0, a=1, file=tmp_file)

    res = allocate_experiment("exp", DummyExp(), [spec], s3_client=ds)
    assert res.workflow_run_id == "wr"
    assert isinstance(spec.file, S3Url)
    assert ds.uploaded  # manifest and schema


def test_allocate_experiment_type_error(tmp_path):
    from scythe.allocate import allocate_experiment, ExperimentSpecsMismatchError
    class DummyExp:
        name = "dummy"
        config = type("cfg", (), {"input_validator": MyInput})
        input_validator = MyInput
        _output_validator = MyOutput

    bad_spec = MyOutput()  # type: ignore[arg-type]
    with pytest.raises(ExperimentSpecsMismatchError):
        allocate_experiment("exp", DummyExp(), [bad_spec], s3_client=DummyS3())


def test_worker_config(monkeypatch):
    from scythe.worker import WorkerNameConfig, ScytheWorkerConfig
    wn = WorkerNameConfig(FLY_REGION="dfw")
    assert wn.fly_hosting_str == "FlyDFW"
    wn = WorkerNameConfig(AWS_BATCH_JOB_ARRAY_INDEX=1)
    assert wn.aws_hosting_str.endswith("0001")
    sw = ScytheWorkerConfig(NAME=None, WORKER_NAME_CONFIG=wn, SLOTS=None, DURABLE_SLOTS=None)
    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    assert sw.computed_slots == 4
    assert sw.computed_durable_slots == 1000
    assert sw.computed_name.startswith("ScytheWorker")

    recorded = []
    class DW:
        def register_workflow(self, wf):
            recorded.append(wf)
        def start(self):
            recorded.append("started")
    monkeypatch.setattr("scythe.worker.hatchet", type("H", (), {"worker": lambda **kw: DW()}))
    monkeypatch.setattr("scythe.worker.ExperimentRegistry", type("ER", (), {"experiments": staticmethod(lambda: ["wf"]), "Register": staticmethod(lambda: (lambda f: f))}))
    sw.start([lambda x: x])
    assert "started" in recorded


