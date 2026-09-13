"""
Build the Gold dimensional model from Silver energy datasets.

Purpose
-------
This module converts validated Silver-layer Ember datasets into a
business-ready dimensional model for analytics in Athena and Power BI.

The Gold model follows a fact-constellation design:

Dimensions
----------
- dim_date
- dim_country
- dim_energy_series

Facts
-----
- fact_generation
- fact_emissions
- fact_demand
- fact_carbon_intensity
- fact_capacity

Key strategy
------------
- date:
  Uses the natural business key stored in the source data.
  No artificial date_id is introduced.

- entity_code:
  Uses the stable country code as the business key.

- series_key:
  Uses a deterministic surrogate key because series names are textual
  business attributes and should not be used directly as fact-table keys.

Design principles
-----------------
- Preserve the natural grain of each business process.
- Keep dimensions reusable across multiple fact tables.
- Avoid unnecessary surrogate keys.
- Keep transformation logic deterministic and reproducible.
- Separate source data from project-specific business classification.
"""

from __future__ import annotations

import hashlib

import pandas as pd
import yaml


# ---------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------

CORE_DATASETS = {
    "generation",
    "demand",
    "emissions",
    "carbon_intensity",
}

SERIES_DATASETS = {
    "generation",
    "emissions",
    "capacity",
}


# ---------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------

def create_series_key(series_name: str) -> int:
    """
    Create a deterministic surrogate key for an energy series.

    Parameters
    ----------
    series_name:
        Business name of an Ember series, for example "Solar",
        "Coal" or "Clean".

    Returns
    -------
    int
        Stable integer surrogate key derived from the series name.

    Why a surrogate key?
    --------------------
    Series names are descriptive business attributes. Using them directly
    as fact-table keys would create wider joins and tighter coupling to
    source naming conventions.

    A deterministic hash is used instead of sequential IDs so that an
    existing key remains stable even if new series are added later.

    Notes
    -----
    Only the first 15 hexadecimal characters are used so the resulting
    value remains within a practical integer range.
    """
    digest = hashlib.sha256(
        series_name.encode("utf-8")
    ).hexdigest()

    return int(digest[:15], 16)


# ---------------------------------------------------------------------
# Dimension builders
# ---------------------------------------------------------------------

def build_dim_date(
    silver_datasets: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Build the monthly date dimension.

    Grain
    -----
    One row per calendar month.

    Source
    ------
    Dates are collected from the four core Silver datasets:
    generation, demand, emissions and carbon intensity.

    Key strategy
    ------------
    The actual date column is used as the natural key.

    No artificial date_id is introduced because the project operates at
    monthly grain and the source date is already stable, unique and useful
    for Power BI time intelligence.

    Returns
    -------
    pandas.DataFrame
        Date dimension containing calendar attributes for reporting.
    """
    dates = pd.concat(
        [
            df[["date"]]
            for name, df in silver_datasets.items()
            if name in CORE_DATASETS
        ],
        ignore_index=True,
    )

    dim_date = (
        dates
        .drop_duplicates()
        .sort_values("date")
        .reset_index(drop=True)
    )

    # Ensure a consistent analytical datetime type.
    dim_date["date"] = pd.to_datetime(
        dim_date["date"],
        errors="raise",
    )

    # Calendar attributes used by Power BI for slicing, grouping
    # and time hierarchies.
    dim_date["year"] = dim_date["date"].dt.year
    dim_date["quarter"] = dim_date["date"].dt.quarter
    dim_date["month_number"] = dim_date["date"].dt.month
    dim_date["month_name"] = dim_date["date"].dt.month_name()
    dim_date["year_month"] = (
        dim_date["date"].dt.strftime("%Y-%m")
    )

    # Mark whether a year contains all twelve monthly observations.
    # This is useful because the current year may only be partially loaded.
    months_per_year = (
        dim_date
        .groupby("year")["month_number"]
        .transform("nunique")
    )

    dim_date["is_complete_year"] = (
        months_per_year == 12
    )

    return dim_date


def build_dim_country(
    silver_datasets: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Build the country dimension.

    Grain
    -----
    One row per country.

    Key strategy
    ------------
    entity_code is used as the business key.

    This is preferable to an artificial surrogate key because the project
    already has stable, compact and meaningful country codes such as DEU,
    FRA and ESP.

    Returns
    -------
    pandas.DataFrame
        Country dimension with country names and project-specific
        business attributes.
    """
    countries = pd.concat(
        [
            df[["entity_code", "entity"]]
            for df in silver_datasets.values()
        ],
        ignore_index=True,
    )

    dim_country = (
        countries
        .drop_duplicates()
        .rename(
            columns={
                "entity": "country_name",
            }
        )
        .sort_values("entity_code")
        .reset_index(drop=True)
    )

    # Project-specific business classification.
    # This attribute is not taken directly from Ember and therefore
    # should remain documented as Gold-layer business logic.
    eu_members = {
        "AUT", "BEL", "CZE", "DEU", "DNK",
        "ESP", "FIN", "FRA", "GRC", "HUN",
        "IRL", "ITA", "NLD", "POL", "PRT",
        "ROU", "SWE",
    }

    dim_country["eu_member_flag"] = (
        dim_country["entity_code"].isin(
            eu_members
        )
    )

    return dim_country


def build_dim_energy_series(
    silver_datasets: dict[str, pd.DataFrame],
    config_path: str,
) -> pd.DataFrame:
    """
    Build the reusable energy-series dimension.

    Grain
    -----
    One row per distinct Ember series.

    Examples
    --------
    Solar
    Wind
    Coal
    Clean
    Fossil
    Total generation

    Source
    ------
    Series values are collected from Silver datasets that contain a
    series column:
    - generation
    - emissions
    - capacity

    Business enrichment
    -------------------
    technology_group and energy_category are read from
    config/series_config.yaml.

    These attributes represent project-specific business semantics and
    are deliberately kept outside the source data.

    Key strategy
    ------------
    series_key is a deterministic surrogate key generated from series_name.

    Returns
    -------
    pandas.DataFrame
        Energy-series dimension used by multiple fact tables.
    """
    series_frames = []

    for dataset_name in SERIES_DATASETS:
        df = silver_datasets[dataset_name]

        series_frames.append(
            df[
                [
                    "series",
                    "is_aggregate_series",
                ]
            ]
        )

    dim_series = (
        pd.concat(
            series_frames,
            ignore_index=True,
        )
        .drop_duplicates()
        .sort_values("series")
        .reset_index(drop=True)
    )

    # Load Gold-layer business classifications.
    with open(
        config_path,
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(file)

    series_config = config["series"]

    # Stable technical key used by fact tables.
    dim_series["series_key"] = (
        dim_series["series"]
        .map(create_series_key)
    )

    # Business attributes are looked up from YAML.
    # Unknown future series are kept but explicitly classified
    # as "Unclassified" instead of failing silently.
    dim_series["technology_group"] = (
        dim_series["series"]
        .map(
            lambda series_name: series_config.get(
                series_name,
                {},
            ).get(
                "technology_group",
                "Unclassified",
            )
        )
    )

    dim_series["energy_category"] = (
        dim_series["series"]
        .map(
            lambda series_name: series_config.get(
                series_name,
                {},
            ).get(
                "energy_category",
                "Unclassified",
            )
        )
    )

    return (
        dim_series[
            [
                "series_key",
                "series",
                "technology_group",
                "energy_category",
                "is_aggregate_series",
            ]
        ]
        .rename(
            columns={
                "series": "series_name",
            }
        )
    )


# ---------------------------------------------------------------------
# Shared fact-table helpers
# ---------------------------------------------------------------------

def add_series_key(
    df: pd.DataFrame,
    dim_energy_series: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add the surrogate series key to a Silver dataset.

    Parameters
    ----------
    df:
        Silver dataset containing a 'series' column.

    dim_energy_series:
        Gold energy-series dimension.

    Returns
    -------
    pandas.DataFrame
        Input dataset enriched with series_key.

    Integrity rule
    --------------
    validate="many_to_one" enforces that each business series name maps
    to exactly one dimension record.

    If duplicate series names exist in the dimension, pandas raises an
    error instead of silently producing duplicated fact rows.
    """
    lookup = dim_energy_series[
        [
            "series_key",
            "series_name",
        ]
    ]

    return df.merge(
        lookup,
        left_on="series",
        right_on="series_name",
        how="left",
        validate="many_to_one",
    )


# ---------------------------------------------------------------------
# Fact builders
# ---------------------------------------------------------------------

def build_fact_generation(
    df: pd.DataFrame,
    dim_energy_series: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the electricity-generation fact table.

    Grain
    -----
    One country × one month × one energy series.

    Foreign keys
    ------------
    date
        References dim_date.date.

    entity_code
        References dim_country.entity_code.

    series_key
        References dim_energy_series.series_key.

    Measures
    --------
    generation_twh
    share_of_generation_pct
    """
    fact = add_series_key(
        df,
        dim_energy_series,
    )

    return fact[
        [
            "date",
            "entity_code",
            "series_key",
            "generation_twh",
            "share_of_generation_pct",
        ]
    ].copy()


def build_fact_emissions(
    df: pd.DataFrame,
    dim_energy_series: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the power-sector-emissions fact table.

    Grain
    -----
    One country × one month × one energy series.

    Measures
    --------
    emissions_mtco2
    share_of_emissions_pct
    """
    fact = add_series_key(
        df,
        dim_energy_series,
    )

    return fact[
        [
            "date",
            "entity_code",
            "series_key",
            "emissions_mtco2",
            "share_of_emissions_pct",
        ]
    ].copy()


def build_fact_demand(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the electricity-demand fact table.

    Grain
    -----
    One country × one month.

    Foreign keys
    ------------
    date
        References dim_date.date.

    entity_code
        References dim_country.entity_code.

    Measure
    -------
    demand_twh
    """
    return df[
        [
            "date",
            "entity_code",
            "demand_twh",
        ]
    ].copy()


def build_fact_carbon_intensity(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the carbon-intensity fact table.

    Grain
    -----
    One country × one month.

    Measure
    -------
    emissions_intensity_gco2_per_kwh
    """
    return df[
        [
            "date",
            "entity_code",
            "emissions_intensity_gco2_per_kwh",
        ]
    ].copy()


def build_fact_capacity(
    df: pd.DataFrame,
    dim_energy_series: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the installed-capacity fact table.

    Grain
    -----
    One country × one month × one energy series.

    Important limitation
    --------------------
    Capacity has narrower country and technology coverage than the four
    core datasets. This source limitation is intentionally preserved.

    Measures
    --------
    capacity_gw
    capacity_w_per_capita
    """
    fact = add_series_key(
        df,
        dim_energy_series,
    )

    return fact[
        [
            "date",
            "entity_code",
            "series_key",
            "capacity_gw",
            "capacity_w_per_capita",
        ]
    ].copy()


# ---------------------------------------------------------------------
# Gold model orchestration
# ---------------------------------------------------------------------

def build_gold_model(
    silver_datasets: dict[str, pd.DataFrame],
    config_path: str,
) -> dict[str, pd.DataFrame]:
    """
    Build the complete Gold-layer dimensional model.

    Parameters
    ----------
    silver_datasets:
        Dictionary containing the validated Silver DataFrames.

        Expected keys:
        - generation
        - demand
        - emissions
        - carbon_intensity
        - capacity

    config_path:
        Path to series_config.yaml containing Gold-layer business
        classifications.

    Returns
    -------
    dict[str, pandas.DataFrame]
        Dictionary containing three dimensions and five fact tables.

    Output model
    ------------
    Dimensions:
        dim_date
        dim_country
        dim_energy_series

    Facts:
        fact_generation
        fact_emissions
        fact_demand
        fact_carbon_intensity
        fact_capacity
    """
    # Build conformed dimensions first because several facts depend on them.
    dim_date = build_dim_date(
        silver_datasets
    )

    dim_country = build_dim_country(
        silver_datasets
    )

    dim_energy_series = build_dim_energy_series(
        silver_datasets,
        config_path,
    )

    # Build fact tables using the shared dimensions.
    return {
        "dim_date": dim_date,
        "dim_country": dim_country,
        "dim_energy_series": dim_energy_series,

        "fact_generation": build_fact_generation(
            silver_datasets["generation"],
            dim_energy_series,
        ),

        "fact_emissions": build_fact_emissions(
            silver_datasets["emissions"],
            dim_energy_series,
        ),

        "fact_demand": build_fact_demand(
            silver_datasets["demand"],
        ),

        "fact_carbon_intensity": (
            build_fact_carbon_intensity(
                silver_datasets["carbon_intensity"],
            )
        ),

        "fact_capacity": build_fact_capacity(
            silver_datasets["capacity"],
            dim_energy_series,
        ),
    }