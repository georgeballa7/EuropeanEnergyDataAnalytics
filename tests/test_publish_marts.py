"""Unit tests for isolated Gold analytics snapshot publishing."""

from unittest.mock import MagicMock

import pytest

from src.analytics import publish_marts as publisher


def test_reject_unknown_mart():
    with pytest.raises(ValueError, match="Unknown analytics mart"):
        publisher.publish_mart("fact_generation")


def test_failed_unload_does_not_change_glue(monkeypatch):
    athena = MagicMock()
    glue = MagicMock()
    monkeypatch.setattr(publisher, "load_mart_sql", lambda name: "SELECT 1 AS value")
    monkeypatch.setattr(publisher, "source_fingerprint", lambda client, sql: "test-fingerprint")
    monkeypatch.setattr(publisher, "get_columns", lambda client, sql: [
        {"Name": "value", "Type": "integer"}
    ])

    def failed_execute(client, query):
        raise RuntimeError("UNLOAD failed")

    monkeypatch.setattr(publisher, "execute", failed_execute)
    with pytest.raises(RuntimeError, match="UNLOAD failed"):
        publisher.publish_mart("generation_demand_summary", athena=athena, glue=glue)
    glue.create_table.assert_not_called()
    glue.update_table.assert_not_called()


def test_empty_snapshot_does_not_change_glue(monkeypatch):
    athena = MagicMock()
    glue = MagicMock()
    monkeypatch.setattr(publisher, "load_mart_sql", lambda name: "SELECT 1 AS value")
    monkeypatch.setattr(publisher, "source_fingerprint", lambda client, sql: "test-fingerprint")
    monkeypatch.setattr(publisher, "get_columns", lambda client, sql: [
        {"Name": "value", "Type": "integer"}
    ])
    monkeypatch.setattr(publisher, "execute", lambda client, query: "query-id")
    athena.get_query_results.return_value = {"ResultSet": {"Rows": [
        {"Data": [{"VarCharValue": "total_rows"}]},
        {"Data": [{"VarCharValue": "0"}]},
    ]}}
    with pytest.raises(ValueError, match="Empty analytics snapshot"):
        publisher.publish_mart("generation_demand_summary", athena=athena, glue=glue)
    assert glue.create_table.call_count == 1
    staging = glue.create_table.call_args.kwargs["TableInput"]["Name"]
    assert staging.startswith("_staging_analytics_")
    glue.delete_table.assert_called_once_with(
        DatabaseName=publisher.DATABASE_NAME, Name=staging
    )
    glue.update_table.assert_not_called()


def test_failed_athena_query_raises():
    client = MagicMock()
    client.get_query_execution.return_value = {
        "QueryExecution": {"Status": {
            "State": "FAILED", "StateChangeReason": "AccessDenied"
        }}
    }
    with pytest.raises(RuntimeError, match="AccessDenied"):
        publisher.wait_for_query(client, "query-id")


def test_unchanged_source_skips_publication(monkeypatch):
    athena = MagicMock()
    glue = MagicMock()
    monkeypatch.setattr(publisher, "load_mart_sql", lambda name: "SELECT 1")
    monkeypatch.setattr(publisher, "source_fingerprint", lambda client, sql: "same")
    glue.get_table.return_value = {"Table": {
        "Parameters": {"analytics_fingerprint": "same", "analytics_row_count": "38"},
        "StorageDescriptor": {"Location": "s3://bucket/existing/"},
    }}
    result = publisher.publish_mart("generation_demand_summary", athena=athena, glue=glue)
    assert result["skipped"] is True
    assert result["rows"] == 38
    athena.start_query_execution.assert_not_called()
    glue.create_table.assert_not_called()
    glue.update_table.assert_not_called()


def test_fingerprint_is_independent_of_row_order(monkeypatch):
    athena = MagicMock()
    monkeypatch.setattr(publisher, "execute", lambda client, sql: "query")
    metadata = {"ColumnInfo": [{"Name": "country_name", "Type": "varchar"}]}

    def response(values):
        return {"ResultSet": {"ResultSetMetadata": metadata, "Rows": [
            {"Data": [{"VarCharValue": "country_name"}]},
            *[{"Data": [{"VarCharValue": value}]} for value in values],
        ]}}

    athena.get_query_results.return_value = response(["Germany", "Austria"])
    first = publisher.source_fingerprint(athena, "SELECT country_name")
    athena.get_query_results.return_value = response(["Austria", "Germany"])
    second = publisher.source_fingerprint(athena, "SELECT country_name")
    assert first == second


def test_glue_type_conversion():
    assert publisher.glue_compatible_type("varchar") == "string"
    assert publisher.glue_compatible_type("varchar(100)") == "string"
    assert publisher.glue_compatible_type("integer") == "int"
    assert publisher.glue_compatible_type("decimal(12,2)") == "decimal(12,2)"
    assert publisher.glue_compatible_type("double") == "double"


def test_get_columns_uses_glue_compatible_types(monkeypatch):
    athena = MagicMock()
    monkeypatch.setattr(publisher, "execute", lambda client, sql: "query")
    athena.get_query_results.return_value = {
        "ResultSet": {"ResultSetMetadata": {"ColumnInfo": [
            {"Name": "country_name", "Type": "varchar"},
            {"Name": "start_year", "Type": "integer"},
            {"Name": "generation_twh", "Type": "double"},
        ]}}
    }
    assert publisher.get_columns(athena, "SELECT 1") == [
        {"Name": "country_name", "Type": "string"},
        {"Name": "start_year", "Type": "int"},
        {"Name": "generation_twh", "Type": "double"},
    ]


def _prepared(name, previous=None, skipped=False):
    return {
        "mart": name, "rows": 38, "location": f"s3://bucket/{name}/",
        "skipped": skipped, "previous_table": previous,
        "table_input": None if skipped else {"Name": publisher.mart_table_name(name)},
    }


def test_prepare_failure_does_not_publish_any_table(monkeypatch):
    glue = MagicMock()
    names = list(publisher.REPORTING_MARTS)
    attempted = []

    def prepare(name, **kwargs):
        attempted.append(name)
        if name == names[2]:
            raise RuntimeError("prepare failed")
        return _prepared(name)

    monkeypatch.setattr(publisher, "prepare_mart", prepare)
    with pytest.raises(RuntimeError, match="prepare failed"):
        publisher.publish_all_marts(athena=MagicMock(), glue=glue)
    assert attempted == names[:3]
    glue.create_table.assert_not_called()
    glue.update_table.assert_not_called()


def test_all_snapshots_prepared_before_any_publication(monkeypatch):
    names = list(publisher.REPORTING_MARTS)
    events = []
    glue = MagicMock()

    def prepare(name, **kwargs):
        events.append(("prepare", name))
        return _prepared(name)

    def publish(item, client):
        events.append(("publish", item["mart"]))

    monkeypatch.setattr(publisher, "prepare_mart", prepare)
    monkeypatch.setattr(publisher, "_publish_prepared", publish)
    result = publisher.publish_all_marts(athena=MagicMock(), glue=glue)
    assert events == [("prepare", n) for n in names] + [("publish", n) for n in names]
    assert len(result) == 4


def test_publish_failure_rolls_back_in_reverse_order(monkeypatch):
    names = list(publisher.REPORTING_MARTS)
    events = []
    monkeypatch.setattr(
        publisher, "prepare_mart",
        lambda name, **kwargs: _prepared(name, previous={
            "Name": publisher.mart_table_name(name),
            "StorageDescriptor": {"Location": f"s3://old/{name}/"},
            "Parameters": {},
        }),
    )

    def publish(item, glue):
        events.append(("publish", item["mart"]))
        if item["mart"] == names[2]:
            raise RuntimeError("update failed")

    def rollback(item, glue):
        events.append(("rollback", item["mart"]))

    monkeypatch.setattr(publisher, "_publish_prepared", publish)
    monkeypatch.setattr(publisher, "_rollback_prepared", rollback)
    with pytest.raises(RuntimeError, match="update failed"):
        publisher.publish_all_marts(athena=MagicMock(), glue=MagicMock())
    assert events == (
        [("publish", n) for n in names[:3]]
        + [("rollback", n) for n in reversed(names[:3])]
    )


def test_rollback_failure_is_reported(monkeypatch):
    names = list(publisher.REPORTING_MARTS)
    monkeypatch.setattr(publisher, "prepare_mart", lambda name, **kwargs: _prepared(name))

    def publish(item, glue):
        if item["mart"] == names[1]:
            raise ValueError("original failure")

    def rollback(item, glue):
        if item["mart"] == names[0]:
            raise RuntimeError("rollback denied")

    monkeypatch.setattr(publisher, "_publish_prepared", publish)
    monkeypatch.setattr(publisher, "_rollback_prepared", rollback)
    with pytest.raises(RuntimeError, match="rollback incomplete.*rollback denied") as err:
        publisher.publish_all_marts(athena=MagicMock(), glue=MagicMock())
    assert isinstance(err.value.__cause__, ValueError)


def test_skipped_marts_are_not_published_or_rolled_back(monkeypatch):
    names = list(publisher.REPORTING_MARTS)
    glue = MagicMock()
    monkeypatch.setattr(
        publisher, "prepare_mart",
        lambda name, **kwargs: _prepared(name, skipped=True),
    )
    result = publisher.publish_all_marts(athena=MagicMock(), glue=glue)
    assert len(result) == len(names)
    assert all(item["skipped"] for item in result)
    glue.create_table.assert_not_called()
    glue.update_table.assert_not_called()


def test_restore_table_input_removes_glue_read_only_fields():
    original = {
        "Name": "analytics_example", "CreateTime": "read-only",
        "DatabaseName": "db", "StorageDescriptor": {"Location": "s3://old/"},
        "Parameters": {"analytics_fingerprint": "old"},
    }
    restored = publisher._restore_table_input(original)
    assert "CreateTime" not in restored
    assert "DatabaseName" not in restored
    assert restored["StorageDescriptor"]["Location"] == "s3://old/"
