"""
Data-quality checks for the Gold dimensional model.

The checks focus on dimensional-model integrity:

1. Dimension keys must be unique.
2. Fact-table grains must be unique.
3. Foreign keys must resolve to the corresponding dimensions.
4. Required measure columns must not contain unexpected null values.
"""

from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------
# Model metadata
# ---------------------------------------------------------------------

DIMENSION_KEYS = {
    "dim_date": ["date"],
    "dim_country": ["entity_code"],
    "dim_energy_series": ["series_key"],
    "dim_capacity_series": ["capacity_series_key"],
}


FACT_GRAINS = {
    "fact_generation": [
        "date",
        "entity_code",
        "series_key",
    ],
    "fact_emissions": [
        "date",
        "entity_code",
        "series_key",
    ],
    "fact_demand": [
        "date",
        "entity_code",
    ],
    "fact_carbon_intensity": [
        "date",
        "entity_code",
    ],
    "fact_capacity": [
        "date",
        "entity_code",
        "capacity_series_key",
    ],
}


FACT_MEASURES = {
    "fact_generation": [
        "generation_twh",
        "share_of_generation_pct",
    ],
    "fact_emissions": [
        "emissions_mtco2",
        "share_of_emissions_pct",
    ],
    "fact_demand": [
        "demand_twh",
    ],
    "fact_carbon_intensity": [
        "emissions_intensity_gco2_per_kwh",
    ],
    "fact_capacity": [
        "capacity_gw",
        "capacity_w_per_capita",
    ],
}


# ---------------------------------------------------------------------
# Generic checks
# ---------------------------------------------------------------------

def count_duplicate_keys(
    df: pd.DataFrame,
    key_columns: list[str],
) -> int:
    """
    Count rows that violate the expected table key or grain.
    """
    return int(
        df.duplicated(
            subset=key_columns,
            keep=False,
        ).sum()
    )


def count_nulls(
    df: pd.DataFrame,
    columns: list[str],
) -> dict[str, int]:
    """
    Count null values for selected columns.
    """
    return {
        column: int(df[column].isna().sum())
        for column in columns
    }


# ---------------------------------------------------------------------
# Dimension validation
# ---------------------------------------------------------------------

def validate_dimensions(
    gold_datasets: dict[str, pd.DataFrame],
) -> dict:
    """
    Validate uniqueness and completeness of dimension keys.
    """
    results = {}

    for table_name, key_columns in DIMENSION_KEYS.items():

        df = gold_datasets[table_name]

        duplicate_keys = count_duplicate_keys(
            df,
            key_columns,
        )

        null_keys = count_nulls(
            df,
            key_columns,
        )

        passed = (
            duplicate_keys == 0
            and all(
                count == 0
                for count in null_keys.values()
            )
        )

        results[table_name] = {
            "passed": passed,
            "duplicate_keys": duplicate_keys,
            "null_keys": null_keys,
        }

    return results


# ---------------------------------------------------------------------
# Fact validation
# ---------------------------------------------------------------------

def validate_facts(
    gold_datasets: dict[str, pd.DataFrame],
) -> dict:
    """
    Validate fact-table grain and required measures.
    """
    results = {}

    for table_name, grain_columns in FACT_GRAINS.items():

        df = gold_datasets[table_name]

        duplicate_grain = count_duplicate_keys(
            df,
            grain_columns,
        )

        null_grain = count_nulls(
            df,
            grain_columns,
        )

        null_measures = count_nulls(
            df,
            FACT_MEASURES[table_name],
        )

        passed = (
            duplicate_grain == 0
            and all(
                count == 0
                for count in null_grain.values()
            )
            and all(
                count == 0
                for count in null_measures.values()
            )
        )

        results[table_name] = {
            "passed": passed,
            "duplicate_grain": duplicate_grain,
            "null_grain": null_grain,
            "null_measures": null_measures,
        }

    return results


# ---------------------------------------------------------------------
# Referential-integrity checks
# ---------------------------------------------------------------------

def validate_foreign_keys(
    gold_datasets: dict[str, pd.DataFrame],
) -> dict:
    """
    Check that fact-table foreign keys resolve to the correct dimensions.

    Generation and emissions resolve series_key against dim_energy_series.
    Capacity resolves capacity_series_key against dim_capacity_series.
    """
    valid_dates = set(
        gold_datasets["dim_date"]["date"]
    )

    valid_countries = set(
        gold_datasets["dim_country"]["entity_code"]
    )

    valid_series = set(
        gold_datasets[
            "dim_energy_series"
        ]["series_key"]
    )

    valid_capacity_series = set(
        gold_datasets[
            "dim_capacity_series"
        ]["capacity_series_key"]
    )

    results = {}

    for table_name, df in gold_datasets.items():

        if not table_name.startswith("fact_"):
            continue

        orphan_dates = (
            ~df["date"].isin(valid_dates)
        ).sum()

        orphan_countries = (
            ~df["entity_code"].isin(valid_countries)
        ).sum()

        orphan_series = 0
        orphan_capacity_series = 0

        if "series_key" in df.columns:
            orphan_series = (
                ~df["series_key"].isin(valid_series)
            ).sum()

        if "capacity_series_key" in df.columns:
            orphan_capacity_series = (
                ~df["capacity_series_key"].isin(
                    valid_capacity_series
                )
            ).sum()

        passed = (
            orphan_dates == 0
            and orphan_countries == 0
            and orphan_series == 0
            and orphan_capacity_series == 0
        )

        results[table_name] = {
            "passed": passed,
            "orphan_dates": int(orphan_dates),
            "orphan_countries": int(orphan_countries),
            "orphan_series": int(orphan_series),
            "orphan_capacity_series": int(
                orphan_capacity_series
            ),
        }

    return results


# ---------------------------------------------------------------------
# Complete Gold-model validation
# ---------------------------------------------------------------------

def validate_gold_model(
    gold_datasets: dict[str, pd.DataFrame],
) -> dict:
    """
    Run all Gold-layer data-quality checks.

    Returns
    -------
    dict
        Validation results for dimensions, facts and foreign keys.
    """

    dimension_results = validate_dimensions(
        gold_datasets
    )

    fact_results = validate_facts(
        gold_datasets
    )

    foreign_key_results = validate_foreign_keys(
        gold_datasets
    )

    all_results = (
        list(dimension_results.values())
        + list(fact_results.values())
        + list(foreign_key_results.values())
    )

    passed = all(
        result["passed"]
        for result in all_results
    )

    return {
        "passed": passed,
        "dimensions": dimension_results,
        "facts": fact_results,
        "foreign_keys": foreign_key_results,
    }
