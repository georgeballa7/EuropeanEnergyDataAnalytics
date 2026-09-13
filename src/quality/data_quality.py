"""
Datenqualitätsprüfungen für die bereinigten Energiedatensätze.

Dieses Modul enthält wiederverwendbare Prüfungen für die Silver-Schicht.
Im Mittelpunkt stehen die fachlich erwartete Tabellenstruktur, eindeutige
Business Keys, vollständige Pflichtfelder und der vereinbarte Länderscope.

Wichtig
-------
Ein bestandener Datenqualitätstest bedeutet, dass ein Datensatz die für ihn
definierten strukturellen Regeln erfüllt. Er bedeutet nicht automatisch, dass
alle Datensätze dieselbe zeitliche oder geografische Abdeckung besitzen. Das
ist insbesondere für den Capacity-Datensatz relevant, dessen Quellabdeckung
geringer ist als die der Core-Datensätze.
"""

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
    """
    Ermittle fehlende Pflichtspalten eines Datensatzes.

    Als Pflichtspalten gelten der definierte Business Key sowie die für den
    jeweiligen Datensatz erwarteten Messgrößen.

    Rückgabe
    --------
    list[str]
        Namen aller erwarteten Spalten, die im DataFrame fehlen.
    """
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
    """
    Zähle Zeilen mit duplizierten Business Keys.

    Der Business Key beschreibt die erwartete fachliche Granularität des
    jeweiligen Silver-Datensatzes. Ein Wert größer als null weist daher auf
    eine Verletzung dieser Granularität hin.
    """
    keys = BUSINESS_KEYS[dataset_name]

    return int(
        df.duplicated(subset=keys).sum()
    )


def count_nulls(
    df: pd.DataFrame,
    dataset_name: str,
) -> dict[str, int]:
    """
    Zähle Nullwerte in Business-Key- und Messspalten.

    Es werden nur Spalten geprüft, die tatsächlich im DataFrame vorhanden
    sind. Fehlende Pflichtspalten werden separat durch
    ``check_required_columns`` erkannt.
    """
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
    """
    Ermittle Länder außerhalb des konfigurierten Projektumfangs.

    Die Prüfung meldet unerwartete Länder, verlangt aber bewusst nicht, dass
    jeder Datensatz sämtliche erwarteten Länder enthält. Dadurch kann etwa
    der Capacity-Datensatz trotz eingeschränkter Quellabdeckung strukturell
    valide sein.
    """
    actual = set(df["entity_code"].dropna().unique())
    expected = set(expected_countries)

    return sorted(actual - expected)


def validate_dataset(
    df: pd.DataFrame,
    dataset_name: str,
    expected_countries: list[str],
) -> dict:
    """
    Führe die definierten Datenqualitätsprüfungen für einen Datensatz aus.

    Geprüft werden:

    1. Vorhandensein aller Pflichtspalten.
    2. Eindeutigkeit des Business Keys.
    3. Nullwerte in Business-Key- und Messspalten.
    4. Länder außerhalb des erwarteten Projektumfangs.

    Rückgabe
    --------
    dict
        Strukturierte Prüfergebnisse einschließlich Zeilenanzahl,
        Detailergebnissen und dem Gesamtstatus ``passed``.
    """
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