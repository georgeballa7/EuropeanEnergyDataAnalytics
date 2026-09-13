"""
Bronze-zu-Silver-Transformationen für Ember-Energiedatensätze.

Dieses Modul standardisiert Datentypen und wendet den analytischen
Projektumfang an. Dabei bleiben die während der EDA identifizierten
fachlichen Eigenschaften der Quelldaten erhalten.

Statistische Ausreißer werden nicht entfernt und fehlende Werte werden nicht
künstlich imputiert.
"""

import pandas as pd


# ---------------------------------------------------------------------
# Projektkonfiguration
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
# Datensatzspezifische Schemadefinitionen
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
# Validierung
# ---------------------------------------------------------------------

def validate_dataset_name(dataset_name: str) -> None:
    """
    Prüfe, ob der angeforderte Datensatz unterstützt wird.

    Raises
    ------
    ValueError
        Wenn der Datensatzname unbekannt ist.
    """
    if dataset_name not in SUPPORTED_DATASETS:
        raise ValueError(
            f"Unsupported dataset: '{dataset_name}'. "
            f"Expected one of: {sorted(SUPPORTED_DATASETS)}"
        )


# ---------------------------------------------------------------------
# Gemeinsame Transformationen
# ---------------------------------------------------------------------

def standardize_common_columns(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Standardisiere die von allen Ember-Datensätzen gemeinsam genutzten Spalten."""
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

    # Quelldatumswerte in analytisch nutzbare datetime-Werte umwandeln.
    df["date"] = pd.to_datetime(
        df["date"],
        errors="raise",
    )

    # Explizite pandas-String-Datentypen verwenden.
    df["entity"] = df["entity"].astype("string")
    df["entity_code"] = df["entity_code"].astype("string")

    return df


# ---------------------------------------------------------------------
# Datensatzspezifische Typtransformationen
# ---------------------------------------------------------------------

def standardize_dataset_types(
    df: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Standardisiere numerische, boolesche und Reihen-Spalten eines Datensatzes.

    Die numerische Konvertierung verwendet eine strikte Fehlerbehandlung.
    Unerwartete Quellwerte führen dadurch zum Abbruch der Transformation,
    anstatt stillschweigend in fehlende Werte umgewandelt zu werden.
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
# Projektumfang
# ---------------------------------------------------------------------

def apply_project_scope(
    df: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Wende den analytischen Zeitumfang des Projekts an.

    Die vier Core-Datensätze werden auf Januar 2010 und später begrenzt.

    Capacity behält seine ursprüngliche Quellabdeckung, da dieser Datensatz
    später beginnt und eine eingeschränktere Länder- und Technologieabdeckung
    besitzt.
    """
    df = df.copy()

    if dataset_name in CORE_DATASETS:
        df = df[
            df["date"] >= PROJECT_START_DATE
        ].copy()

    return df


# ---------------------------------------------------------------------
# Sortierung
# ---------------------------------------------------------------------

def sort_silver_data(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Sortiere Silver-Daten in eine deterministische analytische Reihenfolge."""
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
# Haupttransformation
# ---------------------------------------------------------------------

def clean_energy_data(
    df: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Transformiere einen Ember-Bronze-DataFrame in einen Silver-fähigen DataFrame.

    Transformationsschritte
    -----------------------
    1. Datensatznamen validieren.
    2. Gemeinsame Spalten standardisieren.
    3. Datensatzspezifische Datentypen standardisieren.
    4. Analytischen Projektumfang anwenden.
    5. Ergebnis deterministisch sortieren.

    Wichtige aus der EDA abgeleitete Regeln
    ---------------------------------------
    - Statistische Ausreißer bleiben erhalten.
    - Negative Net Imports bleiben erhalten.
    - Generation Shares werden nicht global auf 0–100 begrenzt.
    - Aggregate-Series-Indikatoren bleiben erhalten.
    - Fehlende Beobachtungen werden nicht künstlich imputiert.
    - Capacity behält seine ursprüngliche, eingeschränktere Abdeckung.
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