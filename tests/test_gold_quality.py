import pandas as pd

from src.quality.gold_quality import (
    validate_dimensions,
    validate_facts,
    validate_foreign_keys,
    validate_gold_model,
)


def valid_gold_datasets():
    date = pd.Timestamp("2026-07-01")
    return {
        "dim_date": pd.DataFrame({"date": [date]}),
        "dim_country": pd.DataFrame({"entity_code": ["DEU"]}),
        "dim_energy_series": pd.DataFrame({"series_key": [1]}),
        "dim_capacity_series": pd.DataFrame({"capacity_series_key": [1]}),
        "fact_generation": pd.DataFrame({
            "date": [date], "entity_code": ["DEU"], "series_key": [1],
            "generation_twh": [8.0], "share_of_generation_pct": [10.0],
        }),
        "fact_emissions": pd.DataFrame({
            "date": [date], "entity_code": ["DEU"], "series_key": [1],
            "emissions_mtco2": [2.0], "share_of_emissions_pct": [5.0],
        }),
        "fact_demand": pd.DataFrame({
            "date": [date], "entity_code": ["DEU"], "demand_twh": [40.0],
        }),
        "fact_carbon_intensity": pd.DataFrame({
            "date": [date], "entity_code": ["DEU"],
            "emissions_intensity_gco2_per_kwh": [100.0],
        }),
        "fact_capacity": pd.DataFrame({
            "date": [date], "entity_code": ["DEU"], "capacity_series_key": [1],
            "capacity_gw": [20.0], "capacity_w_per_capita": [240.0],
        }),
    }


def test_gold_dq_detects_orphan_country_foreign_key():
    gold = valid_gold_datasets()
    gold["fact_generation"].loc[0, "entity_code"] = "FRA"
    result = validate_foreign_keys(gold)
    assert result["fact_generation"]["passed"] is False
    assert result["fact_generation"]["orphan_countries"] == 1


def test_gold_dq_detects_duplicate_dimension_key():
    gold = valid_gold_datasets()
    gold["dim_country"] = pd.concat([gold["dim_country"]] * 2, ignore_index=True)
    result = validate_dimensions(gold)
    assert result["dim_country"]["passed"] is False
    assert result["dim_country"]["duplicate_keys"] == 2


def test_gold_dq_detects_duplicate_fact_grain():
    gold = valid_gold_datasets()
    gold["fact_generation"] = pd.concat([gold["fact_generation"]] * 2, ignore_index=True)
    result = validate_facts(gold)
    assert result["fact_generation"]["passed"] is False
    assert result["fact_generation"]["duplicate_grain"] == 2


def test_gold_dq_detects_null_fact_measure():
    gold = valid_gold_datasets()
    gold["fact_generation"].loc[0, "generation_twh"] = None
    result = validate_facts(gold)
    assert result["fact_generation"]["passed"] is False
    assert result["fact_generation"]["null_measures"]["generation_twh"] == 1


def test_gold_model_accepts_valid_constellation():
    result = validate_gold_model(valid_gold_datasets())
    assert result["passed"] is True
    assert all(x["passed"] for x in result["dimensions"].values())
    assert all(x["passed"] for x in result["facts"].values())
    assert all(x["passed"] for x in result["foreign_keys"].values())


def test_gold_model_rejects_invalid_constellation():
    gold = valid_gold_datasets()
    gold["fact_capacity"].loc[0, "capacity_series_key"] = 99
    result = validate_gold_model(gold)
    assert result["passed"] is False
    assert result["foreign_keys"]["fact_capacity"]["orphan_capacity_series"] == 1
