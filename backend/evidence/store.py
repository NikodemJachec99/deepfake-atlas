"""Magazyn dowodów adresowany treścią. Ten sam plik zapisany dwa razy to jeden obiekt."""

import hashlib
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .models import Artifact


class LocalBackend:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def write(self, key: str, data: bytes, content_type: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class S3Backend:
    def __init__(self) -> None:
        import boto3

        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
        )
        existing = {b["Name"] for b in self.client.list_buckets().get("Buckets", [])}
        if self.bucket not in existing:
            self.client.create_bucket(Bucket=self.bucket)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError:
            return False
        return True

    def write(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type or "application/octet-stream")

    def read(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()


@lru_cache(maxsize=4)
def _backend(name: str, root: str):
    return S3Backend() if name == "s3" else LocalBackend(Path(root))


def backend():
    return _backend(settings.ARTIFACT_BACKEND, str(settings.ARTIFACT_DIR))


def put(data: bytes, kind: str, content_type: str = "", source_url: str = "") -> Artifact:
    sha = hashlib.sha256(data).hexdigest()
    key = f"{sha[:2]}/{sha[2:4]}/{sha}"
    artifact, created = Artifact.objects.get_or_create(
        sha256=sha,
        defaults={"kind": kind, "content_type": content_type, "size": len(data), "storage_key": key, "source_url": source_url},
    )
    # Wpis w bazie nie gwarantuje obiektu w magazynie, więc brak uzupełniamy przy każdym zapisie.
    if created or not backend().exists(artifact.storage_key):
        backend().write(artifact.storage_key, data, content_type)
    return artifact


def get(sha256: str) -> bytes:
    return backend().read(Artifact.objects.get(pk=sha256).storage_key)
