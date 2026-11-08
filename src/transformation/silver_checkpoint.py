"""Wiederanlaufbares Bronze→Silver-Manifest für inkrementelle Verarbeitung.

Das Manifest wird erst NACH einem erfolgreichen Silver-Snapshot geschrieben.
Fehlt es, passt der Silver-ETag nicht oder wurden Bronze-Objekte geändert oder
entfernt, wird aus sämtlichen Bronze-Objekten neu aufgebaut. Historische
Backfills werden durch neu aufgetauchte S3-Keys automatisch erkannt.
"""

import json

from botocore.exceptions import ClientError

MANIFEST_VERSION = 1


def manifest_key(dataset_name: str) -> str:
    return f"control/silver/{dataset_name}.json"


def load_silver_manifest(s3_client, bucket: str, dataset_name: str) -> dict | None:
    try:
        response = s3_client.get_object(
            Bucket=bucket, Key=manifest_key(dataset_name)
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    manifest = json.loads(response["Body"].read().decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid Silver manifest: {dataset_name}")
    return manifest


def bronze_identity(obj: dict) -> dict:
    return {"key": obj["Key"], "etag": obj.get("ETag"), "size": obj.get("Size")}


def choose_bronze_keys(
    s3_client, bucket: str, dataset_name: str,
    bronze_objects: list[dict], silver_key: str | None,
) -> tuple[list[str], bool]:
    """Gib (Keys zur Verarbeitung, vollständiger Rebuild nötig) zurück."""
    all_keys = [obj["Key"] for obj in bronze_objects]
    manifest = load_silver_manifest(s3_client, bucket, dataset_name)
    if not manifest or not silver_key:
        return all_keys, True
    if (manifest.get("version") != MANIFEST_VERSION
            or manifest.get("dataset") != dataset_name
            or manifest.get("snapshot_key") != silver_key
            or not manifest.get("snapshot_etag")
            or not isinstance(manifest.get("bronze_objects"), list)):
        return all_keys, True

    try:
        live_etag = s3_client.head_object(Bucket=bucket, Key=silver_key)["ETag"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
            return all_keys, True
        raise
    if live_etag != manifest["snapshot_etag"]:
        # Silver was changed after the manifest was last committed.
        return all_keys, True

    recorded = {entry["key"]: entry for entry in manifest["bronze_objects"]
                if isinstance(entry, dict) and "key" in entry}
    if len(recorded) != len(manifest["bronze_objects"]):
        return all_keys, True
    current = {obj["Key"]: bronze_identity(obj) for obj in bronze_objects}
    # Rebuild on deletion or same-key source correction; a simple merge could
    # otherwise retain records that have vanished from the source object.
    if any(current.get(key) != old for key, old in recorded.items()):
        return all_keys, True
    return [key for key in all_keys if key not in recorded], False


def save_silver_manifest(
    s3_client, bucket: str, dataset_name: str,
    bronze_objects: list[dict], snapshot_key: str, snapshot_etag: str,
) -> None:
    document = {
        "version": MANIFEST_VERSION,
        "dataset": dataset_name,
        "snapshot_key": snapshot_key,
        "snapshot_etag": snapshot_etag,
        "bronze_objects": [bronze_identity(obj) for obj in bronze_objects],
    }
    s3_client.put_object(
        Bucket=bucket,
        Key=manifest_key(dataset_name),
        Body=json.dumps(document, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )
