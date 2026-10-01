"""Private uploaded originals, verified by immutable S3 version and SHA-256."""
import hashlib
import os
import re
import threading
from uuid import UUID, uuid4

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
_REGION = "ap-south-1"
_FIXTURES: dict[tuple[str, str], bytes] = {}
_FIXTURE_LOCK = threading.Lock()
_FIXTURE_MAX_BYTES = 64 * 1024 * 1024


class StorageError(ValueError):
    """Safe error category; no provider exceptions, keys or data in messages."""


def _uuid(value) -> str:
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise StorageError("invalid_owner_or_upload_id") from None
    if normalized != value:
        raise StorageError("invalid_owner_or_upload_id")
    return normalized


def _filename(value) -> str:
    if (not isinstance(value, str) or not value or len(value) > 240
            or value in (".", "..") or re.search(r"[\x00-\x1f\x7f/\\]", value)):
        raise StorageError("invalid_filename")
    return value


def _content_type(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.+-]{0,90}/[a-z0-9][a-z0-9.+-]{0,90}", value):
        raise StorageError("invalid_content_type")
    return value


def _mode() -> str:
    mode = os.environ.get("PORTFOLIO_STORAGE_MODE", "s3")
    if mode == "fixture" and os.environ.get("NODE_ENV") != "production":
        return mode
    if mode != "s3":
        raise StorageError("storage_fixture_forbidden")
    return mode


def _bucket() -> str:
    value = os.environ.get("PORTFOLIO_STORAGE_BUCKET", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", value):
        raise StorageError("storage_unconfigured")
    return value


def _client():
    # Explicit scoped credentials prevent silent IMDS or operator-profile fallback.
    access = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    if not access or not secret or os.environ.get("AWS_REGION", _REGION) != _REGION:
        raise StorageError("storage_credentials_unconfigured")
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", region_name=_REGION, endpoint_url=f"https://s3.{_REGION}.amazonaws.com",
        aws_access_key_id=access, aws_secret_access_key=secret,
        config=Config(connect_timeout=3, read_timeout=10, retries={"total_max_attempts": 1},
                      proxies={}, s3={"addressing_style": "virtual"}),
    )


def _key(owner, upload, sha):
    return f"private/users/{owner}/uploads/{upload}/{sha}"


def _validated_ref(owner_id: str, ref: dict) -> dict:
    owner = _uuid(owner_id)
    if not isinstance(ref, dict) or ref.get("owner_id") != owner:
        raise StorageError("upload_owner_mismatch")
    upload = _uuid(ref.get("upload_id"))
    sha = ref.get("sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
        raise StorageError("invalid_upload_reference")
    if ref.get("key") != _key(owner, upload, sha):
        raise StorageError("invalid_upload_reference")
    version = ref.get("version_id")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9._+/-]{1,1024}", version) or version == "null":
        raise StorageError("invalid_upload_version")
    size = ref.get("bytes")
    if type(size) is not int or not 0 < size <= MAX_UPLOAD_BYTES:
        raise StorageError("invalid_upload_size")
    _filename(ref.get("filename"))
    _content_type(ref.get("content_type"))
    return ref


def _read_verified(client, bucket: str, ref: dict) -> bytes:
    response = client.get_object(Bucket=bucket, Key=ref["key"], VersionId=ref["version_id"])
    stream = response["Body"]
    try:
        if (response.get("ContentLength") != ref["bytes"]
                or response.get("VersionId") != ref["version_id"]
                or response.get("Metadata", {}).get("sha256") != ref["sha256"]
                or response.get("ContentType") != ref["content_type"]):
            raise StorageError("upload_metadata_mismatch")
        data = stream.read(ref["bytes"] + 1)
        if len(data) != ref["bytes"] or hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise StorageError("upload_hash_mismatch")
        return data
    finally:
        stream.close()


def persist_upload(owner_id: str, upload_id: str, filename: str, data: bytes, content_type: str) -> dict:
    """Return a ref only after exact-version S3 readback verifies all bytes."""
    owner, upload = _uuid(owner_id), _uuid(upload_id)
    name, ctype = _filename(filename), _content_type(content_type)
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_UPLOAD_BYTES:
        raise StorageError("invalid_upload_size")
    sha = hashlib.sha256(data).hexdigest()
    ref = {"owner_id": owner, "upload_id": upload, "key": _key(owner, upload, sha),
           "sha256": sha, "bytes": len(data), "filename": name, "content_type": ctype}
    if _mode() == "fixture":
        ref["version_id"] = "fixture-" + str(uuid4())
        with _FIXTURE_LOCK:
            if sum(map(len, _FIXTURES.values())) + len(data) > _FIXTURE_MAX_BYTES:
                raise StorageError("fixture_capacity_exceeded")
            _FIXTURES[(ref["key"], ref["version_id"])] = data
        return ref
    client = None
    try:
        bucket, client = _bucket(), _client()
        response = client.put_object(Bucket=bucket, Key=ref["key"], Body=data,
                                     ContentType=ctype, ServerSideEncryption="AES256",
                                     Metadata={"sha256": sha, "owner-id": owner, "upload-id": upload})
        ref["version_id"] = response.get("VersionId")
        _validated_ref(owner, ref)
        _read_verified(client, bucket, ref)
        return ref
    except StorageError:
        raise
    except Exception:
        raise StorageError("upload_persistence_failed") from None
    finally:
        if client is not None:
            client.close()


def hydrate_upload(owner_id: str, ref: dict) -> bytes:
    """Authorize owner before I/O, then verify an exact immutable object version."""
    ref = _validated_ref(owner_id, ref)
    if _mode() == "fixture":
        with _FIXTURE_LOCK:
            value = _FIXTURES.get((ref["key"], ref["version_id"]))
        if value is None or len(value) != ref["bytes"] or hashlib.sha256(value).hexdigest() != ref["sha256"]:
            raise StorageError("fixture_upload_missing")
        return value
    client = None
    try:
        client = _client()
        return _read_verified(client, _bucket(), ref)
    except StorageError:
        raise
    except Exception:
        raise StorageError("upload_hydration_failed") from None
    finally:
        if client is not None:
            client.close()
