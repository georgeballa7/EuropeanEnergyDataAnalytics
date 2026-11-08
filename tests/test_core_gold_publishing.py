"""Safe versioned Core Gold publication and Glue rollback tests."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.catalog import glue_catalog
from src.transformation import run_gold_transformation as gold


class MissingTable(Exception):
    pass


class FakeGlue:
    exceptions = SimpleNamespace(EntityNotFoundException=MissingTable)

    def __init__(self, tables=None, events=None, fail_on=None):
        self.tables = deepcopy(tables or {})
        self.events = events if events is not None else []
        self.fail_on = fail_on
        self.failed_once = False

    def get_table(self, DatabaseName, Name):
        if Name not in self.tables:
            raise MissingTable(Name)
        return {"Table": deepcopy(self.tables[Name])}

    def create_table(self, DatabaseName, TableInput):
        self.events.append(("create", TableInput["Name"]))
        self.tables[TableInput["Name"]] = deepcopy(TableInput)
        self._maybe_fail(TableInput["Name"])

    def update_table(self, DatabaseName, TableInput):
        self.events.append(("update", TableInput["Name"]))
        self.tables[TableInput["Name"]] = deepcopy(TableInput)
        self._maybe_fail(TableInput["Name"])

    def delete_table(self, DatabaseName, Name):
        self.events.append(("delete", Name))
        del self.tables[Name]

    def _maybe_fail(self, name):
        # Simulate an ambiguous failure AFTER Glue accepted the write.
        if name == self.fail_on and not self.failed_once:
            self.failed_once = True
            raise RuntimeError("Glue publish failed")


def previous_tables():
    return {
        name: {
            "Name": name,
            "TableType": "EXTERNAL_TABLE",
            "StorageDescriptor": {
                "Location": f"s3://bucket/gold/{name}/",
                "Columns": [{"Name": "id", "Type": "string"}],
            },
            "Parameters": {"classification": "parquet", "legacy": "yes"},
        }
        for name in glue_catalog.GOLD_TABLE_SCHEMAS
    }


def tables_data():
    return {name: pd.DataFrame({"id": [1]})
            for name in glue_catalog.GOLD_TABLE_SCHEMAS}


def setup(monkeypatch, glue):
    monkeypatch.setattr(gold, "dataframe_to_parquet_bytes", lambda df: b"PARQUET")
    s3 = MagicMock()
    def upload(**kwargs):
        glue.events.append(("s3", kwargs["Key"]))
    s3.put_object.side_effect = upload
    return s3


def test_all_nine_snapshots_staged_before_glue_changes(monkeypatch):
    events = []
    glue = FakeGlue(previous_tables(), events)
    s3 = setup(monkeypatch, glue)
    results = gold.write_gold_model(
        s3, tables_data(), glue_client=glue, snapshot_id="run001"
    )
    assert len(results) == 9
    assert [e[0] for e in events[:9]] == ["s3"] * 9
    assert [e[0] for e in events[9:]] == ["update"] * 9
    assert all("/gold_snapshots/" in uri for uri in results)
    for name, item in glue.tables.items():
        assert item["StorageDescriptor"]["Location"] == (
            f"s3://{gold.BUCKET_NAME}/gold_snapshots/{name}/run001/"
        )


def test_failed_staging_keeps_old_glue_tables(monkeypatch):
    old = previous_tables()
    glue = FakeGlue(old)
    s3 = setup(monkeypatch, glue)
    def fail_s3(**kwargs):
        raise RuntimeError("S3 upload failed")
    s3.put_object.side_effect = fail_s3
    with pytest.raises(RuntimeError, match="S3 upload failed"):
        gold.write_gold_model(s3, tables_data(), glue_client=glue, snapshot_id="run002")
    assert glue.tables == old
    assert not any(x[0] in ("update", "create") for x in glue.events)


def test_failed_glue_commit_rolls_back_even_failing_table(monkeypatch):
    old = previous_tables()
    third = list(old)[2]
    glue = FakeGlue(old, fail_on=third)
    s3 = setup(monkeypatch, glue)
    with pytest.raises(RuntimeError, match="Glue publish failed"):
        gold.write_gold_model(s3, tables_data(), glue_client=glue, snapshot_id="run003")
    assert glue.tables == old
    updates = [name for action, name in glue.events if action == "update"]
    assert updates == list(old)[:3] + list(reversed(list(old)[:3]))


def test_catalog_sync_preserves_published_snapshot_path(monkeypatch):
    glue = FakeGlue(previous_tables())
    s3 = setup(monkeypatch, glue)
    gold.write_gold_model(s3, tables_data(), glue_client=glue, snapshot_id="run004")
    locations_before = {
        name: table["StorageDescriptor"]["Location"]
        for name, table in glue.tables.items()
    }
    glue_catalog.update_gold_tables(glue)
    assert {
        name: table["StorageDescriptor"]["Location"]
        for name, table in glue.tables.items()
    } == locations_before
    assert all(table["Parameters"]["core_gold_snapshot_id"] == "run004"
               for table in glue.tables.values())


def test_reject_partial_gold_model_before_s3_writes(monkeypatch):
    glue = FakeGlue()
    s3 = setup(monkeypatch, glue)
    with pytest.raises(ValueError, match="all nine"):
        gold.write_gold_model(s3, {"dim_date": pd.DataFrame()}, glue_client=glue)
    s3.put_object.assert_not_called()


def test_new_environment_can_publish_missing_tables(monkeypatch):
    glue = FakeGlue()
    s3 = setup(monkeypatch, glue)
    gold.write_gold_model(s3, tables_data(), glue_client=glue, snapshot_id="run005")
    assert len(glue.tables) == 9
    assert len([x for x in glue.events if x[0] == "create"]) == 9


def test_versioned_gold_paths_are_outside_legacy_table_prefixes():
    """The old Athena/Glue location must not discover staged snapshots."""
    for name in glue_catalog.GOLD_TABLE_SCHEMAS:
        new_key = gold.build_gold_s3_key(name, "run006")
        assert new_key.startswith(f"gold_snapshots/{name}/run006/")
        assert not new_key.startswith(f"gold/{name}/")
