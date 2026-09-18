import pandas as pd

from src.quality.gold_quality import validate_foreign_keys


def test_gold_dq_detects_orphan_country_foreign_key():
    date = pd.Timestamp("2026-07-01")
    gold_datasets = {
        "dim_date": pd.DataFrame({"date": [date]}),
        "dim_country": pd.DataFrame({"entity_code": ["DEU"]}),
        "dim_energy_series": pd.DataFrame({"series_key": [1]}),
        "dim_capacity_series": pd.DataFrame({"capacity_series_key": [1]}),
        "fact_generation": pd.DataFrame({
            "date": [date],
            "entity_code": ["FRA"],
            "series_key": [1],
        }),
    }

    result = validate_foreign_keys(gold_datasets)

    assert not result["fact_generation"]["passed"]
    assert result["fact_generation"]["orphan_countries"] == 1
