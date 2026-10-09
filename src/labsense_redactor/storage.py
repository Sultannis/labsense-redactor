"""The bucket the backend shares with the redactor: it reads and writes only the keys it's given."""

from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import Settings
from .errors import Unprocessable


class Storage(Protocol):
    def read(self, key: str, max_bytes: int) -> bytes: ...

    def write(self, key: str, body: bytes, content_type: str) -> None: ...


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._client: Any = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(
                s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
                # As the backend's client: checksums only where S3 requires them.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def read(self, key: str, max_bytes: int) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise Unprocessable("not_found") from None
            raise
        if response["ContentLength"] > max_bytes:
            response["Body"].close()
            raise Unprocessable("too_large")
        body: bytes = response["Body"].read()
        return body

    def write(self, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=content_type)


class MemoryStorage:
    """For tests: a dict of keys."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def read(self, key: str, max_bytes: int) -> bytes:
        if key not in self.objects:
            raise Unprocessable("not_found")
        body = self.objects[key][0]
        if len(body) > max_bytes:
            raise Unprocessable("too_large")
        return body

    def write(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = (body, content_type)
