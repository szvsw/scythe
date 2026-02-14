from pathlib import Path

import pandas as pd
import pytest

from scythe.base import (
    ExperimentIndexAdditionalDataDoesNotMatchNRowsError,
    ExperimentIndexAdditionalDataOverlapsWithSpecError,
    ExperimentIndexNotSerializableError,
    ExperimentInputSpec,
    ExperimentOutputSpec,
)
from scythe.types import FileReference, S3Url
from scythe.utils.filesys import fetch_uri
from scythe.utils.results import (
    make_onerow_multiindex_from_dict,
    serialize_df_dict,
    transpose_dataframe_dict,
    save_and_upload_parquets,
)

class MyInputSpec(ExperimentInputSpec):
    a: int
    file: FileReference

class MyOutputSpec(ExperimentOutputSpec):
    b: int | None = None

def test_local_path_and_file_reference_fields(tmp_path):
    spec = MyInputSpec(experiment_id="exp", sort_index=0, file=Path("/tmp/x"), a=1)
    # _file_reference_fields should detect 'file'
    assert spec._file_reference_fields() == ["file"]
    # local_path should put path into cache directory
    uri = S3Url("s3://bucket/foo/bar.txt")
    local = spec.local_path(uri)
    assert str(local).endswith("cache/exp/foo/bar.txt")
    # _local_input_artifact_file_paths should map field name to Path
    paths = spec._local_input_artifact_file_paths
    assert paths == {"file": Path("/tmp/x")}

def test_make_multiindex_basic():
    spec = MyInputSpec(experiment_id="exp", sort_index=1, file=Path("/tmp/f"), a=5)
    mi = spec.make_multiindex({"extra": 42}, n_rows=2)
    assert list(mi.names) == ["experiment_id", "sort_index", "workflow_run_id", "root_workflow_run_id", "a", "file", "extra", "sort_subindex"]
    assert len(mi) == 2
    assert mi.get_level_values("extra")[0] == 42

def test_make_multiindex_errors():
    spec = MyInputSpec(experiment_id="exp", sort_index=0, file=Path("/tmp/f"), a=2)
    with pytest.raises(ExperimentIndexAdditionalDataDoesNotMatchNRowsError):
        spec.make_multiindex([{"x": 1}, {"x": 2}, {"x": 3}], n_rows=2)
    with pytest.raises(ExperimentIndexAdditionalDataOverlapsWithSpecError):
        spec.make_multiindex({"a": 1})
    with pytest.raises(ExperimentIndexAdditionalDataOverlapsWithSpecError):
        spec.make_multiindex([{"a": 1}])
    with pytest.raises(ExperimentIndexNotSerializableError):
        spec.make_multiindex({"bad": set()}, n_rows=1)

def test_add_scalars(tmp_path):
    spec = MyInputSpec(experiment_id="exp", sort_index=0, file=tmp_path/"f", a=3)
    out = MyOutputSpec(dataframes={"d": pd.DataFrame({"x": [1]})}, b=7)
    out.add_scalars(spec)
    assert "scalars" in out.dataframes
    df = out.dataframes["scalars"]
    assert df.iloc[0]["b"] == 7
    # calling again should raise
    with pytest.raises(Exception):
        out.add_scalars(spec)

def test_result_utils(tmp_path):
    df1 = pd.DataFrame({"a": [1]})
    df2 = pd.DataFrame({"a": [2]})
    ser = serialize_df_dict({"first": df1})
    assert ser["first"]["index"] == [0]
    transposed = transpose_dataframe_dict([{"k": df1}, {"k": df2}])
    assert transposed["k"].shape == (2, 1)
    mi = make_onerow_multiindex_from_dict({"a": 1, "b": 2})
    assert list(mi.names) == ["a", "b"]

    class DummyS3:
        def __init__(self):
            self.uploaded = []
        def upload_file(self, Bucket, Key, Filename):
            self.uploaded.append((Bucket, Key, Path(Filename).read_bytes()))

    s3 = DummyS3()
    tmp_df = pd.DataFrame({"a": [3]})
    uris = save_and_upload_parquets({"res": tmp_df}, s3, "bucket", lambda n: f"prefix/{n}.pq")
    assert s3.uploaded and str(uris["res"]).startswith("s3://bucket/prefix")

def test_fetch_uri_file_scheme(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dest = tmp_path / "dst.txt"
    uri = f"file://{src}"
    out = fetch_uri(uri, dest, use_cache=False)
    assert out.read_text() == "hello"
    # repeated call with cache does not overwrite
    src.write_text("changed")
    fetch_uri(uri, dest, use_cache=True)
    assert dest.read_text() == "hello"

    with pytest.raises(FileNotFoundError):
        fetch_uri("file:///nonexistent", dest, use_cache=False)

def test_fetch_uri_http_and_s3(monkeypatch, tmp_path):
    dest = tmp_path / "file.txt"
    # patch requests.get
    class DummyResponse:
        def __init__(self, content):
            self.content = content
    def fake_get(url, timeout):
        return DummyResponse(b"data")
    monkeypatch.setattr("requests.get", fake_get)

    out = fetch_uri("http://example.com/file", dest, use_cache=False)
    assert dest.read_bytes() == b"data"

    # patch s3 client
    downloaded = {}
    class DummyS3:
        def download_file(self, bucket, key, filename):
            downloaded[(bucket, key)] = filename
    ds = DummyS3()
    monkeypatch.setattr("scythe.utils.filesys.s3", ds)
    uri = S3Url("s3://bucket/path/to")
    fetch_uri(uri, dest, use_cache=False, s3=ds)
    assert downloaded[("bucket", "path/to")] == str(dest)


def test_fetch_uri_errors(tmp_path):
    from scythe.utils.filesys import fetch_uri
    from scythe.types import S3Url

    with pytest.raises(ValueError):
        fetch_uri(S3Url("s3://bucket"), tmp_path/"x")
    class DummyAny:
        def __init__(self, url):
            self.scheme = "ftp"
            self.path = "/foo"
    with pytest.raises(NotImplementedError):
        fetch_uri(DummyAny("ftp://x"), tmp_path/"x")

def test_s3_utils(monkeypatch):
    from scythe.utils.s3 import check_experiment_exists, raise_on_forbidden_experiment

    class DS:
        def __init__(self, count):
            self.count = count
        def list_objects_v2(self, Bucket, Prefix):
            return {"KeyCount": self.count}

    ds = DS(1)
    assert check_experiment_exists(ds, "b", "p", "e")
    ds.count = 0
    assert not check_experiment_exists(ds, "b", "p", "e")
    ds.count = 1
    with pytest.raises(ValueError):
        raise_on_forbidden_experiment(ds, "b", "p", "e")
