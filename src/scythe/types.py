"""Types for Scythe."""

from pathlib import Path

from pydantic import AnyUrl, FilePath, HttpUrl, UrlConstraints


class S3Url(AnyUrl):
    """A URL for an S3 object."""

    _constraints = UrlConstraints(allowed_schemes=["s3"], host_required=True)


FileReference = S3Url | HttpUrl | Path | FilePath
