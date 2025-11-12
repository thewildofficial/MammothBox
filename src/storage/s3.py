"""
S3 storage backend stub for future implementation.

This module provides a placeholder for S3-based storage. 
To implement, add boto3 dependency and implement the methods below.
"""

from typing import BinaryIO
from uuid import UUID

from src.storage.adapter import StorageAdapter


class S3Storage(StorageAdapter):
    """
    S3-based storage implementation (stub).

    Future implementation will store files in AWS S3 buckets:
    - s3://{bucket}/incoming/{request_id}/{part_id}/
    - s3://{bucket}/media/clusters/{cluster_id}/{asset_id}/
    - s3://{bucket}/media/derived/{cluster_id}/{asset_id}/

    TODO: Implement with boto3 when S3 support is needed.
    """

    def __init__(
        self,
        bucket: str,
        access_key_id: str = "",
        secret_access_key: str = "",
        region: str = "us-east-1"
    ):
        """
        Initialize S3 storage.

        Args:
            bucket: S3 bucket name
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            region: AWS region
        """
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region

        # TODO: Initialize boto3 client
        # self.s3_client = boto3.client(
        #     's3',
        #     aws_access_key_id=access_key_id,
        #     aws_secret_access_key=secret_access_key,
        #     region_name=region
        # )

        raise NotImplementedError(
            "S3 storage is not yet implemented. Use FilesystemStorage instead."
        )

    def store_raw(self, request_id: str, part_id: str, file: BinaryIO, filename: str) -> str:
        """Store a raw uploaded file (stub)."""
        # TODO: Implement S3 upload
        # key = f"incoming/{request_id}/{part_id}/{filename}"
        # self.s3_client.upload_fileobj(file, self.bucket, key)
        # return f"s3://{self.bucket}/{key}"
        raise NotImplementedError("S3 storage not implemented")

    def store_media(self, cluster_id: UUID, asset_id: UUID, file: BinaryIO, filename: str) -> str:
        """Store a processed media file (stub)."""
        # TODO: Implement S3 upload
        # key = f"media/clusters/{cluster_id}/{asset_id}/{filename}"
        # self.s3_client.upload_fileobj(file, self.bucket, key)
        # return f"s3://{self.bucket}/{key}"
        raise NotImplementedError("S3 storage not implemented")

    def store_derived(self, cluster_id: UUID, asset_id: UUID, file: BinaryIO, filename: str) -> str:
        """Store a derived file (stub)."""
        # TODO: Implement S3 upload
        # key = f"media/derived/{cluster_id}/{asset_id}/{filename}"
        # self.s3_client.upload_fileobj(file, self.bucket, key)
        # return f"s3://{self.bucket}/{key}"
        raise NotImplementedError("S3 storage not implemented")

    def retrieve(self, uri: str) -> BinaryIO:
        """Retrieve a file by its URI (stub)."""
        # TODO: Implement S3 download
        # if not uri.startswith(f"s3://{self.bucket}/"):
        #     raise StorageError(f"Invalid S3 URI: {uri}")
        # key = uri[len(f"s3://{self.bucket}/"):]
        # response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
        # return response['Body']
        raise NotImplementedError("S3 storage not implemented")

    def exists(self, uri: str) -> bool:
        """Check if a file exists (stub)."""
        # TODO: Implement S3 HEAD request
        # try:
        #     key = uri[len(f"s3://{self.bucket}/"):]
        #     self.s3_client.head_object(Bucket=self.bucket, Key=key)
        #     return True
        # except ClientError:
        #     return False
        raise NotImplementedError("S3 storage not implemented")

    def delete(self, uri: str) -> None:
        """Delete a file (stub)."""
        # TODO: Implement S3 deletion
        # key = uri[len(f"s3://{self.bucket}/"):]
        # self.s3_client.delete_object(Bucket=self.bucket, Key=key)
        raise NotImplementedError("S3 storage not implemented")

    def get_size(self, uri: str) -> int:
        """Get file size in bytes (stub)."""
        # TODO: Implement S3 HEAD request
        # key = uri[len(f"s3://{self.bucket}/"):]
        # response = self.s3_client.head_object(Bucket=self.bucket, Key=key)
        # return response['ContentLength']
        raise NotImplementedError("S3 storage not implemented")
