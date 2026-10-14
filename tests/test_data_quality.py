import pandas as pd
import pytest

from src.quality.data_quality import validate_dataset


EXPECTED_COUNTRIES = ["DEU", "FRA"]


def generation_data(**overrides):
    data = {
        "entity_code": ["DEU"],
        "date": pd.to_datetime(["2026-07-01"]),
        "series": ["Solar"],
        "generation_twh": [8.0],
        "share_of_generation_pct": [10.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_silver_dq_detects_missing_required_column():
    df = generation_data().drop(columns=["share_of_generation_pct"])
    result = validate_dataset(df, "generation", EXPECTED_COUNTRIES)
    assert result["passed"] is False
    assert "share_of_generation_pct" in result["missing_columns"]


def test_silver_dq_detects_duplicate_business_key():
    df = pd.concat([generation_data(), generation_data()], ignore_index=True)
    result = validate_dataset(df, "generation", EXPECTED_COUNTRIES)
    assert result["passed"] is False
    assert result["duplicate_keys"] > 0


@pytest.mark.parametrize("column", ["entity_code", "date", "series", "generation_twh", "share_of_generation_pct"])
def test_silver_dq_detects_null_in_required_field(column):
    df = generation_data()
    df.loc[0, column] = None
    result = validate_dataset(df, "generation", EXPECTED_COUNTRIES)
    assert result["passed"] is False
    assert result["null_counts"][column] == 1


def test_silver_dq_detects_unexpected_country():
    result = validate_dataset(generation_data(entity_code=["USA"]), "generation", EXPECTED_COUNTRIES)
    assert result["passed"] is False
    assert result["unexpected_countries"] == ["USA"]


def test_silver_dq_accepts_valid_subset_of_expected_countries():
    result = validate_dataset(generation_data(), "generation", EXPECTED_COUNTRIES)
    assert result["passed"] is True
    assert result["unexpected_countries"] == []
