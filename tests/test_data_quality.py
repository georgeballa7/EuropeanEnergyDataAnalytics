import pandas as pd

from src.quality.data_quality import validate_dataset


EXPECTED_COUNTRIES = ["DEU", "FRA"]


def test_silver_dq_detects_missing_required_column():
    df = pd.DataFrame({
        "entity_code": ["DEU"],
        "date": pd.to_datetime(["2026-07-01"]),
        "series": ["Solar"],
        "generation_twh": [8.0],
    })

    result = validate_dataset(df, "generation", EXPECTED_COUNTRIES)

    assert result["passed"] is False
    assert "share_of_generation_pct" in result["missing_columns"]


def test_silver_dq_detects_duplicate_business_key():
    df = pd.DataFrame({
        "entity_code": ["DEU", "DEU"],
        "date": pd.to_datetime(["2026-07-01", "2026-07-01"]),
        "series": ["Solar", "Solar"],
        "generation_twh": [8.0, 8.0],
        "share_of_generation_pct": [10.0, 10.0],
    })

    result = validate_dataset(df, "generation", EXPECTED_COUNTRIES)

    assert result["passed"] is False
    assert result["duplicate_keys"] > 0
