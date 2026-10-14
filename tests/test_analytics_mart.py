"""Unit tests for additive Gold reporting mart configuration and SQL loading."""

from pathlib import Path

import pytest

from src.analytics.mart_config import REPORTING_MARTS, mart_s3_uri, mart_table_name
from src.analytics.sql_loader import load_mart_sql


def test_reporting_marts_are_isolated_from_core_gold():
    assert len(REPORTING_MARTS) == 4
    for name in REPORTING_MARTS:
        assert mart_s3_uri(name).split("/", 3)[-1].startswith("gold/analytics/")
        assert mart_table_name(name).startswith("analytics_")


@pytest.mark.parametrize("name", list(REPORTING_MARTS))
def test_sql_loader_reads_registered_queries(name):
    repository_sql = Path(__file__).resolve().parents[1] / "sql" / "analytics"
    sql = load_mart_sql(name, repository_sql)
    assert sql
    assert not sql.endswith(";")


def test_unregistered_mart_rejected():
    with pytest.raises(ValueError, match="Unknown analytics mart"):
        load_mart_sql("../../secrets")


def test_sql_loader_rejects_mutating_statements(tmp_path):
    (tmp_path / REPORTING_MARTS["generation_demand_summary"]).write_text(
        "DROP TABLE european_energy_analytics.dim_country", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="SELECT or WITH"):
        load_mart_sql("generation_demand_summary", tmp_path)


def test_sql_loader_rejects_multiple_statements(tmp_path):
    (tmp_path / REPORTING_MARTS["generation_demand_summary"]).write_text(
        "SELECT 1; SELECT 2", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Multiple SQL statements"):
        load_mart_sql("generation_demand_summary", tmp_path)
