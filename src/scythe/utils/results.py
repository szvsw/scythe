"""This module contains functions to postprocess and serialize results."""

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pandas as pd

from scythe.utils import log_interval
from scythe.utils.filesys import S3Url

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
    logger.info(
        "Transposing %d result groups across %d keys",
        len(dataframe_results),
        len(all_keys),
    )
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
    bucket: str,
    output_key_constructor: Callable[[str], str],
    save_errors: bool = False,
) -> dict[str, S3Url]:
    """Save and upload results to s3."""
    logger.info(
        "Saving and uploading %d parquet files to s3://%s", len(collected_dfs), bucket
    )
    uris: dict[str, S3Url] = {}
    log_n = log_interval(len(collected_dfs))
    for i, (key, df) in enumerate(collected_dfs.items()):
        if (i + 1) % log_n == 0:
            logger.info("Uploading %s (%d rows)", key, len(df))
        output_key = output_key_constructor(key)
        if "error" in key.lower() and not save_errors:
            logger.info("Skipping error key %s (save_errors=False)", key)
            continue
        uri = f"s3://{bucket}/{output_key}"
        df.to_parquet(uri)
        uris[key] = S3Url(uri)
        if (i + 1) % log_n == 0:
            logger.info("Uploaded %s (%d rows)", key, len(df))
    return uris


async def save_and_upload_parquets_async(
    collected_dfs: dict[str, pd.DataFrame],
    bucket: str,
    output_key_constructor: Callable[[str], str],
    save_errors: bool = False,
) -> dict[str, S3Url]:
    """Save and upload results to s3 asynchronously."""
    return await asyncio.to_thread(
        save_and_upload_parquets,
        collected_dfs,
        bucket,
        output_key_constructor,
        save_errors,
    )
