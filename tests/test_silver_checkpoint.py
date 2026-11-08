"""Bronze/Silver checkpoint recovery, incremental backfill, and fail-safe tests."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.transformation import run_silver_transformation as silver
from src.transformation import silver_checkpoint as checkpoint


NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def obj(key, etag):
    return {"Key": key, "ETag": etag, "Size": 123, "LastModified": NOW}


def manifest(objects, etag="silver-v1"):
    return {
        "version": 1, "dataset": "generation",
        "snapshot_key": "silver/ember/generation/generation.parquet",
        "snapshot_etag": etag,
        "bronze_objects": [checkpoint.bronze_identity(x) for x in objects],
    }


def plan(monkeypatch, objects, previous):
    monkeypatch.setattr(checkpoint, "load_silver_manifest", lambda *a: previous)
    s3 = MagicMock()
    s3.head_object.return_value = {"ETag": "silver-v1"}
    return checkpoint.choose_bronze_keys(
        s3, "bucket", "generation", objects,
        "silver/ember/generation/generation.parquet"
    )


def test_first_run_rebuilds_all_bronze(monkeypatch):
    objects = [obj("bronze/old.json", "v1"), obj("bronze/new.json", "v2")]
    assert plan(monkeypatch, objects, None) == ([o["Key"] for o in objects], True)


def test_unchanged_snapshot_skips_reprocessing(monkeypatch):
    old = obj("bronze/old.json", "v1")
    assert plan(monkeypatch, [old], manifest([old])) == ([], False)


def test_new_backfill_key_is_processed(monkeypatch):
    old = obj("bronze/old.json", "v1")
    backfill = obj("bronze/historical-backfill.json", "new")
    assert plan(monkeypatch, [old, backfill], manifest([old])) == (
        [backfill["Key"]], False
    )


def test_changed_or_removed_bronze_forces_full_rebuild(monkeypatch):
    old = obj("bronze/old.json", "v1")
    corrected = obj("bronze/old.json", "v2")
    assert plan(monkeypatch, [corrected], manifest([old])) == (
        [corrected["Key"]], True
    )
    assert plan(monkeypatch, [], manifest([old])) == ([], True)


def test_silver_etag_mismatch_forces_full_rebuild(monkeypatch):
    old = obj("bronze/old.json", "v1")
    assert plan(monkeypatch, [old], manifest([old], etag="stale")) == (
        [old["Key"]], True
    )


def test_manifest_written_only_after_successful_silver_upload(monkeypatch):
    old = obj("bronze/old.json", "v1")
    monkeypatch.setattr(silver, "get_bronze_objects", lambda *a: [old])
    monkeypatch.setattr(silver, "get_latest_silver_key", lambda *a: None)
    monkeypatch.setattr(silver, "choose_bronze_keys", lambda *a: ([old["Key"]], True))
    frame = pd.DataFrame({"entity_code": ["DEU"], "date": pd.to_datetime(["2026-09-01"]),
                          "series": ["Solar"], "generation_twh": [1.0]})
    monkeypatch.setattr(silver, "load_bronze_dataframes", lambda *a: [frame])
    monkeypatch.setattr(silver, "clean_energy_data", lambda df, dataset: df)
    monkeypatch.setattr(silver, "get_expected_countries", lambda dataset: ["DEU"])
    monkeypatch.setattr(silver, "validate_dataset", lambda *a: {"passed": True})
    saved = MagicMock()
    monkeypatch.setattr(silver, "save_silver_manifest", saved)
    s3 = MagicMock()
    s3.head_object.return_value = {"ETag": "silver-v2"}

    def failed_write(**kwargs):
        raise RuntimeError("upload failed")

    monkeypatch.setattr(silver, "write_silver_to_s3", failed_write)
    with pytest.raises(RuntimeError, match="upload failed"):
        silver.process_dataset(s3, "generation")
    saved.assert_not_called()

    monkeypatch.setattr(silver, "write_silver_to_s3", lambda **kwargs: "s3://bucket/silver")
    silver.process_dataset(s3, "generation")
    saved.assert_called_once()
    assert saved.call_args.args[-1] == "silver-v2"
