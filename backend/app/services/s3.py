import logging
import boto3
from botocore.exceptions import ClientError
from app.core.config import get_settings
from botocore.client import Config

logger = logging.getLogger(__name__)
settings = get_settings()


class S3Service:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
            config=Config(signature_version="s3v4"),
            endpoint_url=f"https://s3.{settings.aws_region}.amazonaws.com"
        )
        self.bucket = settings.s3_bucket_name

    def generate_presigned_upload_url(self, s3_key: str, content_type: str, expires_in: int = 3600) -> str:
        """
        Generates a secure PUT presigned URL.
        The client-side application uses this to upload large raw match recordings 
        directly to cloud storage without burdening the API threads.
        """
        return self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": self.bucket, "Key": s3_key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    def generate_presigned_download_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """
        Generates a secure GET presigned URL.
        Used to safely stream or review parsed gameplay video highlights.
        """
        return self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )

    def check_file_exists(self, s3_key: str) -> bool:
        """Checks if an object exists within the target S3 bucket using efficient metadata headers."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError:
            return False

    def download_file(self, s3_key: str, local_path: str) -> None:
        """Downloads a raw video file from S3 to a local scratch path inside the Celery worker."""
        try:
            self.client.download_file(self.bucket, s3_key, local_path)
        except Exception as e:
            logger.error(f"Failed to download asset {s3_key} from S3: {e}")
            raise

    def upload_file(self, local_path: str, s3_key: str) -> None:
        """Uploads a post-processed AI highlight clip back up to cloud storage."""
        try:
            self.client.upload_file(local_path, self.bucket, s3_key)
        except Exception as e:
            logger.error(f"Failed to push asset {s3_key} to S3: {e}")
            raise

    def delete_object(self, s3_key: str) -> None:
        """Evicts an individual object file from the cloud bucket storage container."""
        self.client.delete_object(Bucket=self.bucket, Key=s3_key)

    def delete_objects(self, s3_keys: list[str]) -> None:
        """Performs a highly efficient bulk eviction payload operation on an array of S3 target keys."""
        if not s3_keys:
            return
        self.client.delete_objects(
            Bucket=self.bucket,
            Delete={"Objects": [{"Key": k} for k in s3_keys]},
        )


# Instantiate a singleton instance to be shared across API routers and tasks
s3_service = S3Service()