from unittest.mock import MagicMock

import pytest

from src.quality import athena_quality as aq


def test_query_covers_fact_keys_measures_and_foreign_keys():
    query = aq.build_validation_query("fact_generation")
    assert "GROUP BY date, entity_code, series_key" in query
    assert "generation_twh IS NULL" in query
    assert "dim_country" in query
    assert "dim_energy_series" in query
    assert "dim_date" in query


def test_query_covers_capacity_dimension():
    query = aq.build_validation_query("fact_capacity")
    assert "dim_capacity_series" in query
    assert "capacity_w_per_capita IS NULL" in query


def test_query_covers_dimension_without_foreign_keys():
    query = aq.build_validation_query("dim_country")
    assert "CAST(0 AS BIGINT) AS invalid_foreign_keys" in query


def test_unknown_table_rejected():
    with pytest.raises(ValueError, match="Unknown Gold table"):
        aq.build_validation_query("unexpected")


def mock_client(values, state="SUCCEEDED"):
    client = MagicMock()
    client.start_query_execution.return_value = {"QueryExecutionId": "test-id"}
    client.get_query_execution.return_value = {
        "QueryExecution": {"Status": {"State": state, "StateChangeReason": "query failed"}}
    }
    client.get_query_results.return_value = {
        "ResultSet": {"Rows": [
            {"Data": [{"VarCharValue": x} for x in (
                "total_records", "null_required_fields",
                "invalid_foreign_keys", "duplicate_key_groups"
            )]},
            {"Data": [{"VarCharValue": str(x)} for x in values]},
        ]}
    }
    return client


def test_successful_validation():
    client = mock_client([79569, 0, 0, 0])
    assert aq.execute_validation(client, "fact_generation")["total_records"] == 79569
    assert client.start_query_execution.call_args.kwargs["WorkGroup"] == aq.WORKGROUP


@pytest.mark.parametrize("values", [
    [0, 0, 0, 0],
    [10, 1, 0, 0],
    [10, 0, 1, 0],
    [10, 0, 0, 1],
])
def test_quality_failure_raises(values):
    with pytest.raises(ValueError, match="Gold validation failed"):
        aq.execute_validation(mock_client(values), "fact_generation")


def test_failed_athena_query_raises():
    with pytest.raises(RuntimeError, match="query failed"):
        aq.execute_validation(mock_client([1, 0, 0, 0], state="FAILED"), "fact_generation")


def test_timeout_cancels_query(monkeypatch):
    monkeypatch.setattr(aq, "MAX_POLLS", 1)
    monkeypatch.setattr(aq.time, "sleep", lambda _: None)
    client = mock_client([1, 0, 0, 0], state="RUNNING")
    with pytest.raises(TimeoutError):
        aq.execute_validation(client, "fact_generation")
    client.stop_query_execution.assert_called_once_with(QueryExecutionId="test-id")
