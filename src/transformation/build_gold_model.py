"""
Erzeuge das dimensionale Gold-Modell aus validierten Silver-Energiedaten.

Zweck
-----
Dieses Modul überführt validierte Ember-Datensätze aus der Silver-Schicht in
ein fachlich aufbereitetes dimensionales Modell für Analysen mit Athena und
Power BI.

Das Gold-Modell folgt einem Fact-Constellation- bzw. Galaxy-Schema:

Dimensionen
-----------
- dim_date
- dim_country
- dim_energy_series
- dim_capacity_series

Faktentabellen
--------------
- fact_generation
- fact_emissions
- fact_demand
- fact_carbon_intensity
- fact_capacity

Schlüsselstrategie
------------------
- date:
  Verwendet den natürlichen Business Key aus den Quelldaten.
  Es wird kein künstlicher date_id eingeführt.

- entity_code:
  Verwendet den stabilen Ländercode als Business Key.

- series_key:
  Verwendet einen deterministischen Surrogatschlüssel für Reihen aus
  Generation und Emissions.

- capacity_series_key:
  Verwendet einen separaten deterministischen Surrogatschlüssel für
  Capacity-Reihen, da diese trotz identischer fachlicher Bezeichnung andere
  Aggregationssemantiken als Generation und Emissions besitzen können.

Designprinzipien
----------------
- Die natürliche Granularität jedes Geschäftsprozesses bleibt erhalten.
- Dimensionen werden nur dort gemeinsam verwendet, wo die fachliche Semantik
  tatsächlich übereinstimmt.
- Capacity-Reihen bleiben getrennt, wenn die Quellsemantik abweicht.
- Unnötige Surrogatschlüssel werden vermieden.
- Die Transformation bleibt deterministisch und reproduzierbar.
- Quelldaten und projektspezifische fachliche Klassifikation bleiben getrennt.
"""

from __future__ import annotations

import hashlib

import pandas as pd
import yaml


# ---------------------------------------------------------------------
# Modellkonfiguration
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
# Schlüsselerzeugung
# ---------------------------------------------------------------------

def create_series_key(series_name: str) -> int:
    """
    Erzeuge einen deterministischen Surrogatschlüssel für eine Energiereihe.

    Parameter
    ---------
    series_name:
        Fachliche Bezeichnung einer Ember-Reihe, zum Beispiel ``Solar``,
        ``Coal`` oder ``Clean``.

    Rückgabe
    --------
    int
        Stabiler ganzzahliger Surrogatschlüssel, der aus dem Reihennamen
        abgeleitet wird.

    Warum ein Surrogatschlüssel?
    ----------------------------
    Reihennamen sind beschreibende fachliche Attribute. Würden sie direkt als
    Schlüssel in Faktentabellen verwendet, entstünden breitere Joins und eine
    stärkere Kopplung an die Namenskonventionen der Quelle.

    Statt fortlaufender IDs wird ein deterministischer Hash verwendet. Dadurch
    bleibt ein bestehender Schlüssel stabil, auch wenn später neue Reihen
    hinzukommen.

    Hinweise
    --------
    Es werden nur die ersten 15 hexadezimalen Zeichen verwendet, damit der
    resultierende Wert in einem praktikablen Integer-Bereich bleibt.
    """
    digest = hashlib.sha256(
        series_name.encode("utf-8")
    ).hexdigest()

    return int(digest[:15], 16)


# ---------------------------------------------------------------------
# Aufbau der Dimensionen
# ---------------------------------------------------------------------

def build_dim_date(
    silver_datasets: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Erzeuge die monatliche Datumsdimension.

    Granularität
    ------------
    Eine Zeile pro Kalendermonat.

    Quelle
    ------
    Die Datumswerte werden aus den vier Core-Silver-Datensätzen gesammelt:
    Generation, Demand, Emissions und Carbon Intensity.

    Schlüsselstrategie
    ------------------
    Die tatsächliche Spalte ``date`` wird als natürlicher Schlüssel verwendet.

    Ein künstlicher ``date_id`` wird nicht eingeführt, da das Projekt auf
    monatlicher Granularität arbeitet und das Quelldatum bereits stabil,
    eindeutig und für Power-BI-Zeitlogik geeignet ist.

    Rückgabe
    --------
    pandas.DataFrame
        Datumsdimension mit Kalenderattributen für Reporting und Analyse.
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
    Erzeuge die Länderdimension.

    Granularität
    ------------
    Eine Zeile pro Land.

    Schlüsselstrategie
    ------------------
    ``entity_code`` wird als Business Key verwendet.

    Rückgabe
    --------
    pandas.DataFrame
        Länderdimension mit Ländernamen und projektspezifischen fachlichen
        Attributen.
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
    Erzeuge die gemeinsame Energiereihen-Dimension für Generation und Emissions.

    Granularität
    ------------
    Eine Zeile pro eindeutiger Ember-Reihe aus Generation bzw. Emissions.

    Quelle
    ------
    Reihennamen werden ausschließlich aus folgenden Datensätzen übernommen:
    - generation
    - emissions

    Capacity wird bewusst ausgeschlossen, da eine gleich benannte Reihe dort
    eine andere Aggregationssemantik besitzen kann. Beispielsweise ist ``Wind``
    bei Generation/Emissions nicht aggregiert, bei Capacity jedoch aggregiert.

    Fachliche Anreicherung
    ----------------------
    ``technology_group`` und ``energy_category`` werden aus
    ``config/series_config.yaml`` gelesen.

    Schlüsselstrategie
    ------------------
    ``series_key`` ist ein deterministischer Surrogatschlüssel, der aus
    ``series_name`` erzeugt wird.
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
    Erzeuge die Reihendimension für installierte Kapazität.

    Granularität
    ------------
    Eine Zeile pro eindeutiger Capacity-Reihe.

    Warum eine separate Dimension?
    ------------------------------
    Capacity-Reihen teilen nicht immer dieselbe Aggregationssemantik wie
    gleich benannte Reihen aus Generation bzw. Emissions. Eine eigene
    Dimension verhindert mehrdeutige Zuordnungen und duplizierte Faktzeilen.

    Schlüsselstrategie
    ------------------
    ``capacity_series_key`` ist ein deterministischer Surrogatschlüssel aus
    einem Capacity-spezifischen Namespace und dem Reihennamen.
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
# Gemeinsame Hilfsfunktionen für Faktentabellen
# ---------------------------------------------------------------------

def add_series_key(
    df: pd.DataFrame,
    dim_energy_series: pd.DataFrame,
) -> pd.DataFrame:
    """
    Ergänze einen Silver-Datensatz um den Surrogatschlüssel der Energiereihe.

    ``validate="many_to_one"`` stellt sicher, dass jeder fachliche Reihenname
    genau einem Dimensionsdatensatz für Generation/Emissions zugeordnet wird.
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
    Ergänze Silver-Capacity-Daten um den passenden Surrogatschlüssel.

    ``validate="many_to_one"`` stellt sicher, dass jeder Capacity-Reihenname
    genau einem Datensatz der Capacity-Dimension zugeordnet wird.
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
# Aufbau der Faktentabellen
# ---------------------------------------------------------------------

def build_fact_generation(
    df: pd.DataFrame,
    dim_energy_series: pd.DataFrame,
) -> pd.DataFrame:
    """
    Erzeuge die Faktentabelle zur Stromerzeugung.

    Granularität
    ------------
    Ein Land × ein Monat × eine Energiereihe.
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
    Erzeuge die Faktentabelle für Emissionen des Stromsektors.

    Granularität
    ------------
    Ein Land × ein Monat × eine Energiereihe.
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
    Erzeuge die Faktentabelle für Stromnachfrage.

    Granularität
    ------------
    Ein Land × ein Monat.
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
    Erzeuge die Faktentabelle für CO₂-Intensität.

    Granularität
    ------------
    Ein Land × ein Monat.
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
    Erzeuge die Faktentabelle für installierte Kapazität.

    Granularität
    ------------
    Ein Land × ein Monat × eine Capacity-Reihe.

    Wichtige Einschränkung
    ----------------------
    Capacity besitzt eine geringere Länder- und Technologieabdeckung als die
    vier Core-Datensätze. Diese Einschränkung der Quelle wird bewusst erhalten.
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
# Orchestrierung des Gold-Modells
# ---------------------------------------------------------------------

def build_gold_model(
    silver_datasets: dict[str, pd.DataFrame],
    config_path: str,
) -> dict[str, pd.DataFrame]:
    """
    Erzeuge das vollständige dimensionale Modell der Gold-Schicht.

    Rückgabe
    --------
    dict[str, pandas.DataFrame]
        Dictionary mit vier Dimensionen und fünf Faktentabellen.
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
