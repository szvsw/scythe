"""Utilities for interacting with S3."""

from typing import TYPE_CHECKING, Literal

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client as S3ClientType
else:
    S3ClientType = object


# create a singleton s3 client
s3_client: S3ClientType = boto3.client("s3")


def check_experiment_exists(
    s3: S3ClientType, bucket: str, bucket_prefix: str, experiment_id: str
) -> bool:
    """Check if an experiment exists in S3."""
    obj_count = s3.list_objects_v2(
        Bucket=bucket, Prefix=f"{bucket_prefix}/{experiment_id}"
    ).get("KeyCount", 0)
    return obj_count > 0


def raise_on_forbidden_experiment(
    s3: S3ClientType,
    bucket: str,
    bucket_prefix: str,
    experiment_id: str,
    existing_artifacts: Literal["forbid", "overwrite"] = "forbid",
) -> None:
    """Raise an error if an experiment exists in S3."""
    if existing_artifacts == "forbid" and check_experiment_exists(
        s3, bucket, bucket_prefix, experiment_id
    ):
        msg = f"Experiment {experiment_id} already exists (bucket: {bucket}, bucket_prefix: {bucket_prefix})"
        raise ValueError(msg)
