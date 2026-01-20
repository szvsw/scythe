"""Filesystem utilities."""

import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

try:
    # python 3.11+
    from typing import Self  # pyright: ignore [reportAttributeAccessIssue]
except ImportError:
    # python 3.10
    from typing_extensions import Self  # noqa: UP035

import requests
from pydantic import AnyUrl, BaseModel, FilePath, HttpUrl, UrlConstraints

from scythe.utils.s3 import s3_client as s3

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client as S3ClientType
else:
    S3ClientType = object

logger = logging.getLogger(__name__)


def fetch_uri(  # noqa: C901
    uri: AnyUrl | str,
    local_path: Path,
    use_cache: bool = True,
    logger_fn: Callable = logger.info,
    s3: S3ClientType = s3,
) -> Path:
    """Fetch a file from a uri and return the local path.

    Caching is enabled by default and works by
    checking if the file exists locally before downloading it
    to avoid downloading the same file multiple times.

    Args:
        uri (AnyUrl): The uri to fetch
        local_path (Path): The local path to save the fetched file
        use_cache (bool): Whether to use the cache
        logger_fn (Callable): The logger function to use
        s3 (S3Client): The S3 client to use

    Returns:
        local_path (Path): The local path of the fetched file
    """
    if isinstance(uri, str):
        uri = AnyUrl(uri)
    if uri.scheme == "s3":
        bucket = uri.host
        if not uri.path:
            raise ValueError(f"S3URI:NO_PATH:{uri}")
        if not bucket:
            raise ValueError(f"S3URI:NO_BUCKET:{uri}")
        path = uri.path[1:]
        if not local_path.exists() or not use_cache:
            logger_fn(f"Downloading {uri}...")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, path, str(local_path))
        else:
            logger_fn(f"File {local_path} already exists, skipping download.")
    elif uri.scheme == "http" or uri.scheme == "https":
        if not local_path.exists() or not use_cache:
            logger_fn(f"Downloading {uri}...")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(requests.get(str(uri), timeout=60).content)
        else:
            logger_fn(f"File {local_path} already exists, skipping download.")
    elif uri.scheme == "file":
        if not local_path.exists() or not use_cache:
            logger_fn(f"Copying {uri} to {local_path}...")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if uri.path:
                shutil.copy(uri.path, local_path.as_posix())
            else:
                msg = f"File URI:NO_PATH:{uri}"
                logger_fn(msg)
                raise ValueError(msg)
        else:
            logger_fn(f"File {local_path} already exists, skipping copy.")
    else:
        raise NotImplementedError(f"URI:SCHEME:{uri.scheme}")
    return local_path


class S3Url(AnyUrl):
    """A URL for an S3 object."""

    _constraints = UrlConstraints(allowed_schemes=["s3"], host_required=True)


FileReference = S3Url | HttpUrl | Path | FilePath
OptionalFileReference = FileReference | None


class FileReferenceMixin(BaseModel):
    """A mixin for file reference fields."""

    @classmethod
    def _file_reference_fields(cls) -> list[str]:
        """Get the file reference fields."""
        annotations = cls.model_fields
        return [
            k
            for k, v in annotations.items()
            if (
                (v.annotation is FileReference)
                or (v.annotation is OptionalFileReference)
            )
        ]

    @property
    def _local_artifact_file_paths(self) -> dict[str, Path]:
        """Get the local source file paths."""
        data = self.model_dump(exclude_none=True)
        return {
            k: data[k]
            for k in self._file_reference_fields()
            if isinstance(data[k], Path)
        }

    @property
    def remote_artifact_file_paths(self) -> dict[str, HttpUrl | S3Url]:
        """Get the remote source file paths."""
        data = self.model_dump(exclude_none=True)
        return {
            k: data[k]
            for k in self._file_reference_fields()
            if not isinstance(data[k], Path)
        }

    def _copy_local_files_to_and_reference(self, pth: Path) -> Self:
        """Copy the local files to a given path."""
        local_paths = self._local_artifact_file_paths
        new_self = self.model_copy(deep=True)
        for k, v in local_paths.items():
            shutil.copy(v, pth / f"{k}{v.suffix}")
            setattr(new_self, k, pth / f"{k}{v.suffix}")
        return new_self
