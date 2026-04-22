"""Tests for configurable scatter/gather collection depth behavior."""

from pathlib import Path

import pandas as pd

from scythe.scatter_gather import (
    SCYTHE_DATAFRAME_REFERENCES_KEY,
    RecursionMap,
    ScatterGatherResult,
    ScatterGatherInput,
)
from scythe.settings import ScytheStorageSettings
from scythe.utils.filesys import S3Url


def _make_payload(recursion_map: RecursionMap) -> ScatterGatherInput:
    """Build a minimal payload for property-level tests."""
    return ScatterGatherInput(
        experiment_id="exp/test",
        task_name="does_not_matter_for_property_tests",
        specs_uri=S3Url("s3://bucket/specs.pq"),
        storage_settings=ScytheStorageSettings(BUCKET="bucket"),
        recursion_map=recursion_map,
    )


def test_should_materialize_collection_respects_collect_from_depth() -> None:
    """Nodes at or below collect_from_depth should materialize child dataframes."""
    root_payload = _make_payload(
        RecursionMap(path=None, factor=3, max_depth=2, collect_from_depth=1)
    )
    depth_one_payload = _make_payload(
        RecursionMap(
            path=[{"factor": 3, "offset": 0}],
            factor=3,
            max_depth=2,
            collect_from_depth=1,
        )
    )

    assert root_payload.depth == 0
    assert root_payload.should_materialize_collection is False

    assert depth_one_payload.depth == 1
    assert depth_one_payload.should_materialize_collection is True


def test_to_reference_gathered_experiment_runs_from_regular_uris() -> None:
    """Reference gather converts URI mapping into a serializable dataframe."""
    result = ScatterGatherResult(
        uris={
            "scalars": S3Url("s3://bucket/scalars.pq"),
            "result_file_refs": S3Url("s3://bucket/result_file_refs.pq"),
        }
    )

    gathered = result.to_reference_gathered_experiment_runs()
    refs_df = gathered.success.dataframes[SCYTHE_DATAFRAME_REFERENCES_KEY]

    expected = pd.DataFrame(
        [
            {"dataframe_key": "scalars", "uri": "s3://bucket/scalars.pq"},
            {
                "dataframe_key": "result_file_refs",
                "uri": "s3://bucket/result_file_refs.pq",
            },
        ]
    )
    assert refs_df.reset_index(drop=True).equals(expected)


def test_to_reference_gathered_experiment_runs_flattens_existing_reference_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """If the result already points to a reference parquet, it should be reused."""
    existing_refs = pd.DataFrame(
        [
            {"dataframe_key": "scalars", "uri": "s3://bucket/inner_scalars.pq"},
            {"dataframe_key": "metrics", "uri": "s3://bucket/inner_metrics.pq"},
        ]
    )

    def fake_fetch_uri(uri: S3Url, local_path: Path, use_cache: bool = False) -> Path:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        existing_refs.to_parquet(local_path)
        return local_path

    monkeypatch.setattr("scythe.scatter_gather.fetch_uri", fake_fetch_uri)

    result = ScatterGatherResult(
        uris={SCYTHE_DATAFRAME_REFERENCES_KEY: S3Url("s3://bucket/refs_only.pq")}
    )
    gathered = result.to_reference_gathered_experiment_runs()
    refs_df = gathered.success.dataframes[SCYTHE_DATAFRAME_REFERENCES_KEY]

    assert refs_df.reset_index(drop=True).equals(existing_refs)


def test_to_reference_gathered_experiment_runs_falls_back_when_reference_unreadable(
    monkeypatch,
) -> None:
    """Unreadable flattened reference URI should fall back to direct URI listing."""

    def fake_fetch_uri(uri: S3Url, local_path: Path, use_cache: bool = False) -> Path:
        msg = f"unable to fetch {uri}"
        raise RuntimeError(msg)

    monkeypatch.setattr("scythe.scatter_gather.fetch_uri", fake_fetch_uri)

    result = ScatterGatherResult(
        uris={SCYTHE_DATAFRAME_REFERENCES_KEY: S3Url("s3://bucket/refs_only.pq")}
    )
    gathered = result.to_reference_gathered_experiment_runs()
    refs_df = gathered.success.dataframes[SCYTHE_DATAFRAME_REFERENCES_KEY]

    expected = pd.DataFrame(
        [
            {
                "dataframe_key": SCYTHE_DATAFRAME_REFERENCES_KEY,
                "uri": "s3://bucket/refs_only.pq",
            }
        ]
    )
    assert refs_df.reset_index(drop=True).equals(expected)
