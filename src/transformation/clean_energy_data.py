"""
Bronze-to-Silver transformations for Ember energy datasets.

This module standardizes data types and applies the analytical project
scope while preserving the source semantics identified during EDA.

No statistical outliers are removed and no missing values are imputed.
"""

import pandas as pd


# ---------------------------------------------------------------------
# Project configuration
# ---------------------------------------------------------------------

CORE_DATASETS = {
    "generation",
    "demand",
    "emissions",
    "carbon_intensity",
}

SUPPORTED_DATASETS = CORE_DATASETS | {"capacity"}

PROJECT_START_DATE = pd.Timestamp("2010-01-01")


# ---------------------------------------------------------------------
# Dataset-specific schema definitions
# ---------------------------------------------------------------------

DATASET_NUMERIC_COLUMNS = {
    "generation": [
        "generation_twh",
        "share_of_generation_pct",
    ],
    "demand": [
        "demand_twh",
    ],
    "emissions": [
        "emissions_mtco2",
        "share_of_emissions_pct",
    ],
    "carbon_intensity": [
        "emissions_intensity_gco2_per_kwh",
    ],
    "capacity": [
        "capacity_gw",
        "capacity_w_per_capita",
    ],
}


BOOLEAN_COLUMNS = {
    "generation": [
        "is_aggregate_entity",
        "is_aggregate_series",
    ],
    "emissions": [
        "is_aggregate_entity",
        "is_aggregate_series",
    ],
    "capacity": [
        "is_aggregate_entity",
        "is_aggregate_series",
    ],
}


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def validate_dataset_name(dataset_name: str) -> None:
    """
    Ensure that the requested dataset is supported.

    Raises
    ------
    ValueError
        If the dataset name is unknown.
    """
    if dataset_name not in SUPPORTED_DATASETS:
        raise ValueError(
            f"Unsupported dataset: '{dataset_name}'. "
            f"Expected one of: {sorted(SUPPORTED_DATASETS)}"
        )


# ---------------------------------------------------------------------
# Common transformations
# ---------------------------------------------------------------------

def standardize_common_columns(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Standardize columns shared by all Ember datasets.
    """
    df = df.copy()

    required_columns = {
        "entity",
        "entity_code",
        "date",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            "Missing required common columns: "
            f"{sorted(missing_columns)}"
        )

    # Convert source date strings to analytical datetime values.
    df["date"] = pd.to_datetime(
        df["date"],
        errors="raise",
    )

    # Use explicit pandas string types.
    df["entity"] = df["entity"].astype("string")
    df["entity_code"] = df["entity_code"].astype("string")

    return df


# ---------------------------------------------------------------------
# Dataset-specific type transformations
# ---------------------------------------------------------------------

def standardize_dataset_types(
    df: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Standardize numeric, boolean and series columns for a dataset.

    Numeric conversion uses strict error handling so that unexpected
    source values cause the transformation to fail instead of being
    silently converted to missing values.
    """
    df = df.copy()

    numeric_columns = DATASET_NUMERIC_COLUMNS[
        dataset_name
    ]

    missing_numeric_columns = (
        set(numeric_columns) - set(df.columns)
    )

    if missing_numeric_columns:
        raise ValueError(
            f"Missing numeric columns for {dataset_name}: "
            f"{sorted(missing_numeric_columns)}"
        )

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="raise",
        )

    boolean_columns = BOOLEAN_COLUMNS.get(
        dataset_name,
        [],
    )

    missing_boolean_columns = (
        set(boolean_columns) - set(df.columns)
    )

    if missing_boolean_columns:
        raise ValueError(
            f"Missing boolean columns for {dataset_name}: "
            f"{sorted(missing_boolean_columns)}"
        )

    for column in boolean_columns:
        df[column] = df[column].astype("boolean")

    if "series" in df.columns:
        df["series"] = df["series"].astype("string")

    return df


# ---------------------------------------------------------------------
# Project scope
# ---------------------------------------------------------------------

def apply_project_scope(
    df: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Apply the analytical time scope of the project.

    The four core datasets are restricted to January 2010 onwards.

    Capacity retains its original source coverage because the available
    dataset starts later and has more limited country and technology
    coverage.
    """
    df = df.copy()

    if dataset_name in CORE_DATASETS:
        df = df[
            df["date"] >= PROJECT_START_DATE
        ].copy()

    return df


# ---------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------

def sort_silver_data(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Sort Silver data into a deterministic analytical order.
    """
    sort_columns = [
        "entity_code",
        "date",
    ]

    if "series" in df.columns:
        sort_columns.append("series")

    return (
        df
        .sort_values(sort_columns)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------
# Main transformation
# ---------------------------------------------------------------------

def clean_energy_data(
    df: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Transform an Ember Bronze DataFrame into a Silver-ready DataFrame.

    Transformation steps
    --------------------
    1. Validate the dataset name.
    2. Standardize common columns.
    3. Standardize dataset-specific data types.
    4. Apply the analytical project scope.
    5. Sort the result deterministically.

    Important EDA-derived rules
    ---------------------------
    - Statistical outliers are preserved.
    - Negative Net Imports are preserved.
    - Generation shares are not globally restricted to 0-100.
    - Aggregate-series indicators are preserved.
    - Missing observations are not artificially imputed.
    - Capacity retains its original, more limited coverage.
    """
    validate_dataset_name(dataset_name)

    df = standardize_common_columns(df)

    df = standardize_dataset_types(
        df,
        dataset_name,
    )

    df = apply_project_scope(
        df,
        dataset_name,
    )

    df = sort_silver_data(df)

    return df