"""Pagination works beyond S3's first 1,000-object listing page."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.transformation import run_gold_transformation as gold
from src.transformation import run_silver_transformation as silver
from src.utils.s3_listing import latest_object_key


def s3_with_objects(objects):
    s3 = MagicMock()
    s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": objects[:1000]}, {"Contents": objects[1000:]}
    ]
    return s3


def test_latest_object_key_looks_past_first_thousand():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    objects = [
        {"Key": f"silver/ember/generation/old_{i:04d}.parquet",
         "LastModified": base + timedelta(seconds=i)}
        for i in range(1001)
    ]
    objects.append({
        "Key": "silver/ember/generation/ignore.json",
        "LastModified": base + timedelta(days=5),
    })
    s3 = s3_with_objects(objects)
    assert latest_object_key(s3, "bucket", "silver/ember/generation/", ".parquet") == (
        "silver/ember/generation/old_1000.parquet"
    )
    s3.get_paginator.assert_called_once_with("list_objects_v2")
    s3.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="bucket", Prefix="silver/ember/generation/"
    )


def test_silver_no_snapshot_returns_none():
    assert silver.get_latest_silver_key(s3_with_objects([]), "generation") is None


def test_gold_no_snapshot_raises():
    with pytest.raises(FileNotFoundError, match="Keine Silver-Parquet-Datei"):
        gold.get_latest_silver_key(s3_with_objects([]), "generation")


def test_equal_last_modified_is_deterministic():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s3 = s3_with_objects([
        {"Key": "silver/a.parquet", "LastModified": now},
        {"Key": "silver/b.parquet", "LastModified": now},
    ])
    assert latest_object_key(s3, "bucket", "silver/", ".parquet") == "silver/b.parquet"
