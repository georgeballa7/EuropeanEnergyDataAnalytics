"""S3-Objektlisten vollständig (auch über 1.000 Einträge) durchlaufen."""


def latest_object_key(s3_client, bucket: str, prefix: str, suffix: str) -> str | None:
    """Neuesten passenden Key über alle S3-ListObjectsV2-Seiten ermitteln.

    Bei identischem LastModified entscheidet der Key deterministisch.
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    latest = None
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(suffix):
                continue
            if latest is None or (obj["LastModified"], obj["Key"]) > (
                latest["LastModified"], latest["Key"]
            ):
                latest = obj
    return latest["Key"] if latest else None
