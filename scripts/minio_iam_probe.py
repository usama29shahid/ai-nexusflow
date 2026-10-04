"""Prove MinIO IAM policies against a live store. Called by minio-iam-bootstrap.sh.

A small single PUT is not enough: dlt archive uploads use multipart. Root deletes
the probe keys afterward because nexus_loader is denied DeleteObject on the
append-only archive buckets.
"""

from __future__ import annotations

import os
import sys
from typing import Any

PROBE_PREFIX = "_iam_probe/"
PART_SIZE = 5 * 1024 * 1024


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _client(access_key: str, secret_key: str) -> Any:
    import boto3
    from botocore.config import Config

    port = os.environ.get("MINIO_API_PORT", "9002")
    endpoint = os.environ.get("MINIO_ENDPOINT_URL", f"http://localhost:{port}")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _denied(action) -> None:
    from botocore.exceptions import ClientError

    try:
        action()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"AccessDenied", "AccessDeniedException", "AllAccessDisabled"}:
            return
        raise SystemExit(f"Expected AccessDenied, got {code}: {exc}") from exc
    raise SystemExit("Expected AccessDenied, but the call succeeded")


def _complete_multipart(client: Any, bucket: str, key: str, body: bytes) -> None:
    created = client.create_multipart_upload(Bucket=bucket, Key=key)
    upload_id = created["UploadId"]
    part = client.upload_part(
        Bucket=bucket,
        Key=key,
        UploadId=upload_id,
        PartNumber=1,
        Body=body,
    )
    client.complete_multipart_upload(
        Bucket=bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": [{"ETag": part["ETag"], "PartNumber": 1}]},
    )


def _abort_multipart(client: Any, bucket: str, key: str) -> None:
    created = client.create_multipart_upload(Bucket=bucket, Key=key)
    client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=created["UploadId"])


def _cleanup(root: Any, env: str) -> None:
    buckets = (
        f"nexus-dlt-dbt-clickhouse-{env}",
        f"nexus-telemetry-{env}",
        f"nexus-airflow-logs-{env}",
        f"nexus-dlt-dbt-spark-iceberg-archive-{env}",
        f"nexus-dlt-dbt-spark-iceberg-{env}",
    )
    for bucket in buckets:
        _abort_uploads(root, bucket, PROBE_PREFIX)
        _delete_prefix(root, bucket, PROBE_PREFIX)
    _delete_prefix(root, f"nexus-telemetry-{env}", f"indexes/signoz/{PROBE_PREFIX}")


def _delete_prefix(client: Any, bucket: str, prefix: str) -> None:
    token = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents") or []:
            client.delete_object(Bucket=bucket, Key=item["Key"])
        if not page.get("IsTruncated"):
            return
        token = page.get("NextContinuationToken")


def _abort_uploads(client: Any, bucket: str, prefix: str) -> None:
    marker = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if marker:
            kwargs["KeyMarker"] = marker
        page = client.list_multipart_uploads(**kwargs)
        for upload in page.get("Uploads") or []:
            client.abort_multipart_upload(
                Bucket=bucket,
                Key=upload["Key"],
                UploadId=upload["UploadId"],
            )
        if not page.get("IsTruncated"):
            return
        marker = page.get("NextKeyMarker")


def main() -> int:
    env = os.environ.get("NEXUS_ENV", "dev")
    archive = f"nexus-dlt-dbt-clickhouse-{env}"
    telemetry = f"nexus-telemetry-{env}"
    logs = f"nexus-airflow-logs-{env}"
    iceberg_archive = f"nexus-dlt-dbt-spark-iceberg-archive-{env}"
    iceberg = f"nexus-dlt-dbt-spark-iceberg-{env}"
    all_buckets = (archive, telemetry, logs, iceberg_archive, iceberg)

    loader = _client(_required("MINIO_LOADER_USER"), _required("MINIO_LOADER_PASSWORD"))
    reader = _client(_required("MINIO_READER_USER"), _required("MINIO_READER_PASSWORD"))
    platform = _client(
        _required("MINIO_PLATFORM_READER_USER"),
        _required("MINIO_PLATFORM_READER_PASSWORD"),
    )
    admin = _client(_required("MINIO_ADMIN_USER"), _required("MINIO_ADMIN_PASSWORD"))
    root = _client(_required("MINIO_ROOT_USER"), _required("MINIO_ROOT_PASSWORD"))

    archive_key = f"{PROBE_PREFIX}multipart.bin"
    abort_key = f"{PROBE_PREFIX}multipart-abort.bin"
    telemetry_key = f"{PROBE_PREFIX}put.txt"
    logs_key = f"{PROBE_PREFIX}put.txt"
    iceberg_key = f"{PROBE_PREFIX}iceberg.txt"
    marker_key = f"indexes/signoz/{PROBE_PREFIX}marker.txt"
    body = b"nexus-iam-probe-part\n" * (PART_SIZE // 20)

    try:
        print(f"Loader multipart upload on {archive}...")
        _complete_multipart(loader, archive, archive_key, body)
        got = loader.get_object(Bucket=archive, Key=archive_key)
        got["Body"].read()
        print("Loader abort multipart...")
        _abort_multipart(loader, archive, abort_key)
        print("Loader delete on archive must be denied...")
        _denied(lambda: loader.delete_object(Bucket=archive, Key=archive_key))
        print("Loader put/get/delete on Iceberg warehouse...")
        loader.put_object(Bucket=iceberg, Key=iceberg_key, Body=b"iceberg")
        loader.get_object(Bucket=iceberg, Key=iceberg_key)["Body"].read()
        loader.delete_object(Bucket=iceberg, Key=iceberg_key)
        print("Loader put on Iceberg archive; delete must be denied...")
        loader.put_object(
            Bucket=iceberg_archive,
            Key=f"{PROBE_PREFIX}lake-archive.txt",
            Body=b"archive",
        )
        _denied(
            lambda: loader.delete_object(
                Bucket=iceberg_archive,
                Key=f"{PROBE_PREFIX}lake-archive.txt",
            )
        )
        print("Loader put/get on telemetry and airflow logs...")
        loader.put_object(Bucket=telemetry, Key=telemetry_key, Body=b"telemetry")
        loader.get_object(Bucket=telemetry, Key=telemetry_key)["Body"].read()
        print("Loader delete on telemetry must be denied...")
        _denied(lambda: loader.delete_object(Bucket=telemetry, Key=telemetry_key))
        loader.put_object(Bucket=logs, Key=logs_key, Body=b"logs")
        loader.get_object(Bucket=logs, Key=logs_key)["Body"].read()

        print("Reader get telemetry, deny archive put, allow signoz marker...")
        reader.get_object(Bucket=telemetry, Key=telemetry_key)["Body"].read()
        _denied(
            lambda: reader.put_object(
                Bucket=archive,
                Key=f"{PROBE_PREFIX}reader.txt",
                Body=b"nope",
            )
        )
        reader.put_object(Bucket=telemetry, Key=marker_key, Body=b"marker")

        print("Platform reader lists/gets all buckets; put must be denied...")
        for bucket in all_buckets:
            platform.list_objects_v2(Bucket=bucket, MaxKeys=1)
        platform.get_object(Bucket=telemetry, Key=telemetry_key)["Body"].read()
        _denied(
            lambda: platform.put_object(
                Bucket=archive,
                Key=f"{PROBE_PREFIX}platform.txt",
                Body=b"nope",
            )
        )

        print("Admin lists every bucket...")
        for bucket in all_buckets:
            admin.list_objects_v2(Bucket=bucket, MaxKeys=1)
    finally:
        print("Root removing probe keys...")
        _cleanup(root, env)

    print("MinIO IAM probe OK.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"MinIO IAM probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
