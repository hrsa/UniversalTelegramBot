import asyncio
from functools import partial
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from loguru import logger

from app.config import settings


class S3BackupService:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION
        )
        self.bucket_name = settings.AWS_S3_BUCKET_NAME
        self.backup_dir = Path(settings.BACKUP_DIR)

    async def process_backups(self) -> dict:
        stats = {
            "found": 0,
            "uploaded": 0,
            "failed": 0,
            "deleted": 0
        }

        try:
            if not self.backup_dir.exists():
                logger.warning(f"Backup directory {self.backup_dir} does not exist.")
                return stats

            backup_files = list(self.backup_dir.glob("backup_*.sql.gz"))
            stats["found"] = len(backup_files)

            if not backup_files:
                logger.info("No backup files found.")
                return stats

            logger.info(f"Found {len(backup_files)} backup files to process.")

            for backup_file in backup_files:
                try:
                    s3_key = await self._upload_to_s3(backup_file)

                    if s3_key:
                        stats["uploaded"] += 1

                        if await self._delete_local_backup(backup_file):
                            stats["deleted"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    logger.error(f"Failed to upload backup file {backup_file}: {e}")
                    stats["failed"] += 1

            logger.info(
                f"Backup completed. "
                f"Found: {stats['found']}, Uploaded: {stats['uploaded']}, Failed: {stats['failed']}, Deleted: {stats['deleted']}"
            )

            return stats

        except Exception as e:
            logger.error(f"Failed to process backups: {e}")
            return stats

    async def _upload_to_s3(self, file_path: Path) -> str | None:
        try:
            filename = file_path.name

            s3_key = f"backups/{filename}"

            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            logger.info(f"Uploading {filename} ({file_size_mb:.2f} MB) to s3://{self.bucket_name}/{s3_key}")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._upload_file_sync,
                str(file_path),
                self.bucket_name,
                s3_key
            )
            logger.info(f"Backup uploaded successfully to s3://{self.bucket_name}/{s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"Failed to upload backup file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error uploading {file_path}: {e}")
            return None

    def _upload_file_sync(self, file_path: str, bucket: str, key: str) -> None:
        self.s3_client.upload_file(file_path, bucket, key, ExtraArgs={
            'StorageClass': 'STANDARD_IA',
            'ServerSideEncryption': 'AES256'
        })

    async def _delete_local_backup(self, file_path: Path) -> bool:
        try:
            file_path.unlink()
            logger.info(f"Deleted local backup file {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete local backup file {file_path}: {e}")
            return False

    async def list_s3_backups(self, limit: int = 50) -> list[dict]:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self._list_backups_sync,
                self.bucket_name,
                'backups/',
                limit
            )

            backups = []
            for obj in response.get('Contents', []):
                backups.append({
                    'key': obj['Key'],
                    'size_mb': obj['Size'] / (1024 * 1024),
                    'last_modified': obj['LastModified'],
                    'filename': obj['Key'].split('/')[-1]
                })

            backups.sort(key=lambda x: x['last_modified'], reverse=True)
            return backups

        except ClientError as e:
            logger.error(f"Failed to list S3 backups: {e}")
            return []

    def _list_backups_sync(self, bucket_name: str, prefix: str = 'backups/', max_keys: int = 50):
        return self.s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            MaxKeys=max_keys
        )

    async def download_latest_backup(self, destination_path: Optional[Path] = None) -> Optional[Path]:
        try:
            logger.info("Fetching latest backup from S3...")
            backups = await self.list_s3_backups(limit=1)

            if not backups:
                logger.warning("No backups found in S3")
                return None

            latest_backup = backups[0]
            s3_key = latest_backup['key']
            filename = latest_backup['filename']
            size_mb = latest_backup['size_mb']

            logger.info(
                f"Latest backup: {filename} "
                f"({size_mb:.2f} MB, "
                f"modified: {latest_backup['last_modified']})"
            )

            # Determine destination path
            if destination_path is None:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                destination_path = self.backup_dir / filename

            await self.download_backup_by_name(filename, destination_path)

        except ClientError as e:
            logger.error(f"S3 error while downloading backup: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading backup: {e}")
            return None


    async def download_backup_by_name(self, filename: str, destination_path: Optional[Path] = None) -> Optional[Path]:
        try:
            s3_key = f"backups/{filename}"
            logger.info(f"Downloading backup {filename} from s3://{self.bucket_name}/{s3_key}")
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    self._head_object_sync,
                    self.bucket_name,
                    s3_key
                )
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.error(f"Backup {filename} not found in s3://{self.bucket_name}/{s3_key}")
                    return None
                raise

            if destination_path is None:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                destination_path = self.backup_dir / filename

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._download_file_sync,
                self.bucket_name,
                s3_key,
                str(destination_path)
            )
            if destination_path.exists():
                size_mb = destination_path.stat().st_size / (1024 * 1024)
                logger.info(f"Backup {filename} downloaded successfully ({size_mb:.2f} MB)")
                return destination_path
            else:
                logger.error(f"Failed to download backup {filename}, file not found after download")
                return None

        except Exception as e:
            logger.error(f"Failed to download backup {filename}: {e}")
            return None

    def _download_file_sync(self, bucket: str, key: str, destination: str) -> None:
        self.s3_client.download_file(bucket, key, destination)

    def _head_object_sync(self, bucket: str, key: str) -> dict:
        return self.s3_client.head_object(Bucket=bucket, Key=key)
