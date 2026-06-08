import io
import json
import logging
from typing import List, Dict
from app.config import settings

logger = logging.getLogger(__name__)


class MinIOStorage:
    """Handles uploading Parquet files to MinIO."""

    def __init__(self):
        from minio import Minio
        self._client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info(f"Created MinIO bucket: {self._bucket}")

    def upload_parquet(self, records: List[Dict], org_id: str,
                       scan_id: str, object_type: str, page: int) -> str:
        """Converts records to Parquet and uploads to MinIO. Returns object path."""
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq

        df = pd.DataFrame(records)
        table = pa.Table.from_pandas(df)

        buf = io.BytesIO()
        pq.write_table(table, buf)
        buf.seek(0)

        object_path = (f"{org_id}/{scan_id}/{object_type.lower()}/"
                       f"page_{page:03d}.parquet")

        self._client.put_object(
            bucket_name=self._bucket,
            object_name=object_path,
            data=buf,
            length=buf.getbuffer().nbytes,
            content_type="application/octet-stream",
        )
        logger.info(f"Uploaded {len(records)} records to MinIO: {object_path}")
        return f"s3://{self._bucket}/{object_path}"

    def upload_metadata(self, metadata: dict, org_id: str,
                        scan_id: str, object_type: str) -> str:
        """Uploads scan metadata JSON to MinIO."""
        data = json.dumps(metadata, indent=2).encode()
        object_path = f"{org_id}/{scan_id}/{object_type.lower()}/_metadata.json"

        self._client.put_object(
            bucket_name=self._bucket,
            object_name=object_path,
            data=io.BytesIO(data),
            length=len(data),
            content_type="application/json",
        )
        return f"s3://{self._bucket}/{object_path}"


class MockMinIOStorage:
    """Mock MinIO storage for dev — logs operations without real uploads."""

    def upload_parquet(self, records, org_id, scan_id, object_type, page):
        path = f"s3://salesforce-dev/{org_id}/{scan_id}/{object_type.lower()}/page_{page:03d}.parquet"
        logger.info(f"[MOCK MinIO] Would upload {len(records)} records to {path}")
        return path

    def upload_metadata(self, metadata, org_id, scan_id, object_type):
        path = f"s3://salesforce-dev/{org_id}/{scan_id}/{object_type.lower()}/_metadata.json"
        logger.info(f"[MOCK MinIO] Would upload metadata to {path}")
        return path


def create_storage():
    """Factory — returns real or mock MinIO storage."""
    if settings.MINIO_ENABLED:
        try:
            return MinIOStorage()
        except Exception as e:
            logger.warning(f"MinIO unavailable ({e}), using mock storage")
    return MockMinIOStorage()
