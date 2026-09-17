import pandas as pd

from src.transformation.run_silver_transformation import merge_silver_snapshot


def test_initial_load_without_existing_snapshot():
    new = pd.DataFrame({
        "entity_code": ["DEU", "FRA"],
        "date": pd.to_datetime(["2026-07-01", "2026-07-01"]),
        "series": ["Solar", "Solar"],
        "generation_twh": [8.0, 6.0],
    })

    result = merge_silver_snapshot(None, new, "generation")

    assert len(result) == 2
    assert set(result["entity_code"]) == {"DEU", "FRA"}


def test_incremental_merge_preserves_existing_and_new_records():
    current = pd.DataFrame({
        "entity_code": ["DEU"],
        "date": pd.to_datetime(["2026-07-01"]),
        "series": ["Solar"],
        "generation_twh": [8.0],
    })
    new = pd.DataFrame({
        "entity_code": ["DEU", "DEU"],
        "date": pd.to_datetime(["2026-08-01", "2026-09-01"]),
        "series": ["Solar", "Solar"],
        "generation_twh": [9.0, 10.0],
    })

    result = merge_silver_snapshot(current, new, "generation")

    assert len(result) == 3
    assert result["generation_twh"].tolist() == [8.0, 9.0, 10.0]


def test_new_record_replaces_existing_business_key():
    current = pd.DataFrame({
        "entity_code": ["DEU"],
        "date": pd.to_datetime(["2026-07-01"]),
        "series": ["Solar"],
        "generation_twh": [8.0],
    })
    new = pd.DataFrame({
        "entity_code": ["DEU"],
        "date": pd.to_datetime(["2026-07-01"]),
        "series": ["Solar"],
        "generation_twh": [9.5],
    })

    result = merge_silver_snapshot(current, new, "generation")

    assert len(result) == 1
    assert result.iloc[0]["generation_twh"] == 9.5
