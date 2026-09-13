import pandas as pd


BUSINESS_KEYS = {
    "generation": ["entity_code", "date", "series"],
    "demand": ["entity_code", "date"],
    "emissions": ["entity_code", "date", "series"],
    "carbon_intensity": ["entity_code", "date"],
    "capacity": ["entity_code", "date", "series"],
}


MEASUREMENT_COLUMNS = {
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


def check_required_columns(
    df: pd.DataFrame,
    dataset_name: str,
) -> list[str]:
    required = (
        BUSINESS_KEYS[dataset_name]
        + MEASUREMENT_COLUMNS[dataset_name]
    )

    return [
        column
        for column in required
        if column not in df.columns
    ]


def count_duplicate_keys(
    df: pd.DataFrame,
    dataset_name: str,
) -> int:
    keys = BUSINESS_KEYS[dataset_name]

    return int(
        df.duplicated(subset=keys).sum()
    )


def count_nulls(
    df: pd.DataFrame,
    dataset_name: str,
) -> dict[str, int]:
    columns = (
        BUSINESS_KEYS[dataset_name]
        + MEASUREMENT_COLUMNS[dataset_name]
    )

    return {
        column: int(df[column].isna().sum())
        for column in columns
        if column in df.columns
    }


def find_unexpected_countries(
    df: pd.DataFrame,
    expected_countries: list[str],
) -> list[str]:
    actual = set(df["entity_code"].dropna().unique())
    expected = set(expected_countries)

    return sorted(actual - expected)


def validate_dataset(
    df: pd.DataFrame,
    dataset_name: str,
    expected_countries: list[str],
) -> dict:
    missing_columns = check_required_columns(
        df,
        dataset_name,
    )

    result = {
        "dataset": dataset_name,
        "row_count": len(df),
        "missing_columns": missing_columns,
    }

    if missing_columns:
        result["passed"] = False
        return result

    duplicates = count_duplicate_keys(
        df,
        dataset_name,
    )

    nulls = count_nulls(
        df,
        dataset_name,
    )

    unexpected_countries = find_unexpected_countries(
        df,
        expected_countries,
    )

    result.update({
        "duplicate_keys": duplicates,
        "null_counts": nulls,
        "unexpected_countries": unexpected_countries,
        "passed": (
            duplicates == 0
            and all(value == 0 for value in nulls.values())
            and len(unexpected_countries) == 0
        ),
    })

    return result