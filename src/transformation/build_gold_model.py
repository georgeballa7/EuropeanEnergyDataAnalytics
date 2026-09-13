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
- dim_capacity_series

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
  Uses a deterministic surrogate key for generation/emissions series.

- capacity_series_key:
  Uses a separate deterministic surrogate key for capacity series because
  capacity series can have different aggregate semantics from generation
  and emissions even when the business name is identical.

Design principles
-----------------
- Preserve the natural grain of each business process.
- Keep dimensions reusable where business semantics are truly shared.
- Keep capacity series separate where source semantics differ.
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

ENERGY_SERIES_DATASETS = {
    "generation",
    "emissions",
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

    dim_date["date"] = pd.to_datetime(
        dim_date["date"],
        errors="raise",
    )

    dim_date["year"] = dim_date["date"].dt.year
    dim_date["quarter"] = dim_date["date"].dt.quarter
    dim_date["month_number"] = dim_date["date"].dt.month
    dim_date["month_name"] = dim_date["date"].dt.month_name()
    dim_date["year_month"] = (
        dim_date["date"].dt.strftime("%Y-%m")
    )

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
    Build the reusable generation/emissions energy-series dimension.

    Grain
    -----
    One row per distinct generation/emissions Ember series.

    Source
    ------
    Series values are collected only from:
    - generation
    - emissions

    Capacity is deliberately excluded because an identically named series
    can carry different aggregate semantics there. For example, "Wind" is
    non-aggregate in generation/emissions but aggregate in capacity.

    Business enrichment
    -------------------
    technology_group and energy_category are read from
    config/series_config.yaml.

    Key strategy
    ------------
    series_key is a deterministic surrogate key generated from series_name.
    """
    series_frames = []

    for dataset_name in ENERGY_SERIES_DATASETS:
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

    with open(
        config_path,
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(file)

    series_config = config["series"]

    dim_series["series_key"] = (
        dim_series["series"]
        .map(create_series_key)
    )

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


def build_dim_capacity_series(
    capacity_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the installed-capacity series dimension.

    Grain
    -----
    One row per distinct capacity series.

    Why a separate dimension?
    -------------------------
    Capacity series do not always share the same aggregate semantics as
    generation/emissions series with the same name. Keeping a dedicated
    dimension prevents ambiguous mappings and duplicated fact rows.

    Key strategy
    ------------
    capacity_series_key is a deterministic surrogate key generated from a
    capacity-specific namespace plus the series name.
    """
    dim_capacity_series = (
        capacity_df[
            [
                "series",
                "is_aggregate_series",
            ]
        ]
        .drop_duplicates()
        .sort_values("series")
        .reset_index(drop=True)
    )

    dim_capacity_series["capacity_series_key"] = (
        dim_capacity_series["series"]
        .map(
            lambda series_name: create_series_key(
                f"capacity::{series_name}"
            )
        )
    )

    return (
        dim_capacity_series[
            [
                "capacity_series_key",
                "series",
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
    Add the surrogate energy-series key to a Silver dataset.

    validate="many_to_one" ensures every business series name maps to
    exactly one generation/emissions dimension record.
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


def add_capacity_series_key(
    df: pd.DataFrame,
    dim_capacity_series: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add the surrogate capacity-series key to a Silver capacity dataset.

    validate="many_to_one" ensures every capacity series name maps to
    exactly one capacity dimension record.
    """
    lookup = dim_capacity_series[
        [
            "capacity_series_key",
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
    dim_capacity_series: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the installed-capacity fact table.

    Grain
    -----
    One country × one month × one capacity series.

    Important limitation
    --------------------
    Capacity has narrower country and technology coverage than the four
    core datasets. This source limitation is intentionally preserved.
    """
    fact = add_capacity_series_key(
        df,
        dim_capacity_series,
    )

    return fact[
        [
            "date",
            "entity_code",
            "capacity_series_key",
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

    Returns
    -------
    dict[str, pandas.DataFrame]
        Dictionary containing four dimensions and five fact tables.
    """
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

    dim_capacity_series = build_dim_capacity_series(
        silver_datasets["capacity"],
    )

    return {
        "dim_date": dim_date,
        "dim_country": dim_country,
        "dim_energy_series": dim_energy_series,
        "dim_capacity_series": dim_capacity_series,

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
            dim_capacity_series,
        ),
    }
