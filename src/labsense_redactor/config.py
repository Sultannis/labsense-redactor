"""Settings from the environment, read once at startup."""

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """The service token and the bucket. In AWS the task role supplies the S3 credentials."""

    token: str
    s3_bucket: str
    s3_region: str
    s3_endpoint: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_force_path_style: bool = False
    #: The backend sends at most 20 pages and 20 MB; these bound what one request may cost.
    max_pages: int = 50
    max_bytes: int = 30 * 1024 * 1024


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    token = env.get("REDACTOR_TOKEN", "")
    if len(token) < 16:
        raise RuntimeError("REDACTOR_TOKEN must be set (at least 16 characters)")
    bucket = env.get("S3_BUCKET", "")
    if not bucket:
        raise RuntimeError("S3_BUCKET must be set")
    return Settings(
        token=token,
        s3_bucket=bucket,
        s3_region=env.get("S3_REGION", "eu-central-1"),
        s3_endpoint=env.get("S3_ENDPOINT") or None,
        s3_access_key_id=env.get("S3_ACCESS_KEY_ID") or None,
        s3_secret_access_key=env.get("S3_SECRET_ACCESS_KEY") or None,
        s3_force_path_style=env.get("S3_FORCE_PATH_STYLE") == "true",
    )
