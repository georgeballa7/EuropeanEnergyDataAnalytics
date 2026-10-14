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
    glue.create_table.assert_not_called()
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
