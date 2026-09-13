"""
Datenqualitätsprüfungen für das dimensionale Gold-Modell.

Die Prüfungen konzentrieren sich auf die Integrität des dimensionalen Modells:

1. Dimensionsschlüssel müssen eindeutig und vollständig sein.
2. Die Granularität jeder Faktentabelle muss eindeutig sein.
3. Fremdschlüssel müssen auf die zugehörigen Dimensionen auflösbar sein.
4. Erforderliche Messgrößen dürfen keine unerwarteten Nullwerte enthalten.
"""

from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------
# Modellmetadaten
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
# Generische Prüfungen
# ---------------------------------------------------------------------

def count_duplicate_keys(
    df: pd.DataFrame,
    key_columns: list[str],
) -> int:
    """Zähle Zeilen, die den erwarteten Schlüssel bzw. Grain verletzen."""
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
    """Zähle Nullwerte in den ausgewählten Spalten."""
    return {
        column: int(df[column].isna().sum())
        for column in columns
    }


# ---------------------------------------------------------------------
# Validierung der Dimensionen
# ---------------------------------------------------------------------

def validate_dimensions(
    gold_datasets: dict[str, pd.DataFrame],
) -> dict:
    """Prüfe Eindeutigkeit und Vollständigkeit der Dimensionsschlüssel."""
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
# Validierung der Faktentabellen
# ---------------------------------------------------------------------

def validate_facts(
    gold_datasets: dict[str, pd.DataFrame],
) -> dict:
    """Prüfe Grain und erforderliche Messgrößen der Faktentabellen."""
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
# Prüfungen der referenziellen Integrität
# ---------------------------------------------------------------------

def validate_foreign_keys(
    gold_datasets: dict[str, pd.DataFrame],
) -> dict:
    """
    Prüfe, ob Fremdschlüssel der Faktentabellen in den Dimensionen existieren.

    Generation und Emissions lösen ``series_key`` gegen
    ``dim_energy_series`` auf. Capacity löst ``capacity_series_key`` gegen
    ``dim_capacity_series`` auf. Alle Faktentabellen referenzieren außerdem
    gültige Datums- und Länderschlüssel.
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
# Vollständige Validierung des Gold-Modells
# ---------------------------------------------------------------------

def validate_gold_model(
    gold_datasets: dict[str, pd.DataFrame],
) -> dict:
    """
    Führe sämtliche Datenqualitätsprüfungen der Gold-Schicht aus.

    Rückgabe
    --------
    dict
        Strukturierte Prüfergebnisse für Dimensionen, Faktentabellen und
        Fremdschlüssel einschließlich des Gesamtstatus ``passed``.
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
