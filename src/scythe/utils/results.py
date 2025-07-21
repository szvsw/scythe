"""This module contains functions to postprocess and serialize results."""

import logging
import tempfile
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pandas as pd
from pydantic import AnyUrl

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
else:
    S3Client = object

logger = logging.getLogger(__name__)


def serialize_df_dict(dfs: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """Serialize a dictionary of dataframes into a dictionary of dictionaries.

    Args:
        dfs (dict[str, pd.DataFrame]): A dictionary of dataframes

    Returns:
        dict[str, dict]: A dictionary of dictionaries
    """
    return {k: v.to_dict(orient="tight") for k, v in dfs.items()}


def transpose_dataframe_dict(
    dataframe_results: list[dict[str, pd.DataFrame]],
) -> dict[str, pd.DataFrame]:
    """Transpose a list of dictionaries of dataframes into a dictionary of combined dataframes."""
    all_keys = {key for df_dict in dataframe_results for key in df_dict}
    return {
        key: pd.concat(
            [df_dict[key] for df_dict in dataframe_results if key in df_dict], axis=0
        )
        for key in all_keys
    }


def make_onerow_multiindex_from_dict(
    d: dict[str, Any], n_rows: int = 1
) -> pd.MultiIndex:
    """Makes a MultiIndex from a dictionary.

    This is useful for returning a wide-form dataframe of results for a single task.

    Args:
        d (dict[str, Any]): The dictionary to make the MultiIndex from.
        n_rows (int): The number of rows to repeat the MultiIndex.

    Returns:
        multi_index (pd.MultiIndex): The MultiIndex.
    """
    return pd.MultiIndex.from_tuples(
        [tuple(d.values())] * n_rows,
        names=list(d.keys()),
    )


def save_and_upload_parquets(
    collected_dfs: dict[str, pd.DataFrame],
    s3: S3Client,
    bucket: str,
    output_key_constructor: Callable[[str], str],
    save_errors: bool = False,
) -> dict[str, AnyUrl]:
    """Save and upload results to s3."""
    uris: dict[str, AnyUrl] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        for key, df in collected_dfs.items():
            output_key = output_key_constructor(key)
            if "error" in key.lower() and not save_errors:
                continue
            f = f"{tmpdir}/{key}.parquet"
            df.to_parquet(f)
            s3.upload_file(Bucket=bucket, Key=output_key, Filename=f)
            uri = f"s3://{bucket}/{output_key}"
            uris[key] = AnyUrl(uri)
    return uris
