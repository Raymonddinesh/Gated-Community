"""S3-Compatible Object Storage Client Foundation (AWS S3 / MinIO)."""

import logging
from typing import Any

import aioboto3
from botocore.config import Config

from apps.api.src.core.config import get_settings

logger = logging.getLogger("societysphere.storage")


class ObjectStorageClient:
    """Abstract client for S3-compatible blob storage."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.session = aioboto3.Session()
        self.bucket = self.settings.OBJECT_STORAGE_BUCKET

    def _get_client_kwargs(self) -> dict[str, str]:
        kwargs = {
            "service_name": "s3",
            "aws_access_key_id": self.settings.OBJECT_STORAGE_ACCESS_KEY,
            "aws_secret_access_key": self.settings.OBJECT_STORAGE_SECRET_KEY,
            "region_name": self.settings.OBJECT_STORAGE_REGION,
            "config": Config(signature_version="s3v4"),
        }
        if self.settings.OBJECT_STORAGE_ENDPOINT:
            kwargs["endpoint_url"] = self.settings.OBJECT_STORAGE_ENDPOINT
        return kwargs

    async def generate_presigned_upload_url(
        self,
        object_key: str,
        content_type: str = "application/octet-stream",
        expires_in_seconds: int = 300,
    ) -> str | None:
        """Generate short-lived presigned PUT URL for client direct upload."""
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                url = await s3.generate_presigned_url(
                    ClientMethod="put_object",
                    Params={
                        "Bucket": self.bucket,
                        "Key": object_key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=expires_in_seconds,
                )
                return url
        except Exception as exc:
            logger.error(f"Failed to generate presigned upload URL for '{object_key}': {exc}")
            return None

    async def generate_presigned_download_url(
        self,
        object_key: str,
        expires_in_seconds: int = 60,
    ) -> str | None:
        """Generate short-lived presigned GET URL for secure document access."""
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                url = await s3.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={
                        "Bucket": self.bucket,
                        "Key": object_key,
                    },
                    ExpiresIn=expires_in_seconds,
                )
                return url
        except Exception as exc:
            logger.error(f"Failed to generate presigned download URL for '{object_key}': {exc}")
            return None

    async def put_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> bool:
        """Upload raw bytes to private S3 bucket."""
        try:
            kwargs: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": object_key,
                "Body": data,
                "ContentType": content_type,
            }
            if metadata:
                kwargs["Metadata"] = metadata
            async with self.session.client(**self._get_client_kwargs()) as s3:
                await s3.put_object(**kwargs)
                return True
        except Exception as exc:
            logger.error(f"Failed to put object for '{object_key}': {exc}")
            return False

    async def get_object(self, object_key: str) -> bytes | None:
        """Download raw bytes from private S3 bucket."""
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                res = await s3.get_object(Bucket=self.bucket, Key=object_key)
                async with res["Body"] as stream:
                    return await stream.read()
        except Exception as exc:
            logger.error(f"Failed to get object for '{object_key}': {exc}")
            return None

    async def head_object(self, object_key: str) -> dict[str, str] | None:
        """Fetch metadata for an object in S3 bucket."""
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                res = await s3.head_object(Bucket=self.bucket, Key=object_key)
                return res.get("Metadata", {})
        except Exception as exc:
            logger.error(f"Failed to head object for '{object_key}': {exc}")
            return None

    async def check_health(self) -> bool:
        """Probe object storage connectivity."""
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                # Check bucket existence or list buckets
                await s3.list_buckets()
                return True
        except Exception as exc:
            logger.warning(f"Object storage health probe failed: {exc}")
            return False


_storage_client: ObjectStorageClient | None = None


def get_storage_client() -> ObjectStorageClient:
    """Return singleton object storage client."""
    global _storage_client
    if _storage_client is None:
        _storage_client = ObjectStorageClient()
    return _storage_client
