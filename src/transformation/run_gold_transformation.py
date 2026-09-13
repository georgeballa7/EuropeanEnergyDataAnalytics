"""
Führe die Transformation von Silver nach Gold aus.

Pipeline
--------
1. Lade die Silver-Parquet-Datensätze aus Amazon S3.
2. Erzeuge das dimensionale Gold-Modell.
3. Validiere die Integrität des dimensionalen Modells.
4. Brich die Verarbeitung sofort ab, wenn die Gold-DQ fehlschlägt.
5. Schreibe ausschließlich validierte Gold-Tabellen als Parquet nach S3.

Das Modul ist bewusst unabhängig von Notebooks ausführbar und kann dadurch
später als wiederverwendbarer Pipeline-Schritt von Apache Airflow orchestriert
werden.
"""

from __future__ import annotations

import io
from pathlib import Path

import boto3
import pandas as pd

from src.quality.gold_quality import validate_gold_model
from src.transformation.build_gold_model import build_gold_model
from src.transformation.silver_writer import dataframe_to_parquet_bytes


# ---------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------

BUCKET_NAME = (
    "european-energy-data-analytics-488658242500-eu-central-1-an"
)

AWS_PROFILE = "energy-pipeline"
REGION_NAME = "eu-central-1"

SILVER_DATASETS = [
    "generation",
    "demand",
    "emissions",
    "carbon_intensity",
    "capacity",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SERIES_CONFIG_PATH = (
    PROJECT_ROOT / "config" / "series_config.yaml"
)


# ---------------------------------------------------------------------
# AWS-Session
# ---------------------------------------------------------------------

def get_s3_client():
    """
    Erzeuge einen S3-Client mit dem lokalen AWS-Profil des Projekts.

    Hinweise
    --------
    Das benannte Profil ist für die lokale Entwicklung geeignet. Wenn dieser
    Code später innerhalb von Airflow in einer produktiven AWS-Umgebung läuft,
    sollten IAM Roles gegenüber langlebigen Zugangsdaten bevorzugt werden.
    """
    session = boto3.Session(
        profile_name=AWS_PROFILE,
        region_name=REGION_NAME,
    )

    return session.client("s3")


# ---------------------------------------------------------------------
# Silver-Daten laden
# ---------------------------------------------------------------------

def get_latest_silver_key(
    s3_client,
    dataset_name: str,
) -> str:
    """
    Ermittle das zuletzt geschriebene Silver-Parquet-Objekt.

    Parameter
    ---------
    s3_client:
        Konfigurierter boto3-S3-Client.

    dataset_name:
        Name des Silver-Datensatzes, zum Beispiel ``generation``.

    Rückgabe
    --------
    str
        S3-Objektschlüssel der neuesten Parquet-Datei.

    Raises
    ------
    FileNotFoundError
        Wenn für den Datensatz kein Silver-Parquet-Objekt vorhanden ist.

    Wichtig
    -------
    Die aktuelle Silver-Implementierung schreibt vollständige Snapshots. Daher
    repräsentiert das neueste Objekt den aktuellen Silver-Zustand.

    Falls Silver später auf append-only inkrementelle Dateien umgestellt wird,
    muss auch diese Ladestrategie entsprechend angepasst werden.
    """
    prefix = (
        f"silver/ember/{dataset_name}/"
    )

    response = s3_client.list_objects_v2(
        Bucket=BUCKET_NAME,
        Prefix=prefix,
    )

    objects = [
        obj
        for obj in response.get("Contents", [])
        if obj["Key"].endswith(".parquet")
    ]

    if not objects:
        raise FileNotFoundError(
            f"No Silver Parquet file found for "
            f"dataset '{dataset_name}'."
        )

    latest_object = max(
        objects,
        key=lambda obj: obj["LastModified"],
    )

    return latest_object["Key"]


def load_silver_dataset(
    s3_client,
    dataset_name: str,
) -> pd.DataFrame:
    """Lade einen Silver-Parquet-Datensatz aus S3 in einen pandas DataFrame."""
    key = get_latest_silver_key(
        s3_client,
        dataset_name,
    )

    response = s3_client.get_object(
        Bucket=BUCKET_NAME,
        Key=key,
    )

    parquet_bytes = response["Body"].read()

    return pd.read_parquet(
        io.BytesIO(parquet_bytes),
        engine="pyarrow",
    )


def load_all_silver_datasets(
    s3_client,
) -> dict[str, pd.DataFrame]:
    """Lade alle Silver-Datensätze, die für das Gold-Modell benötigt werden."""
    datasets = {}

    for dataset_name in SILVER_DATASETS:
        print(
            f"Loading Silver dataset: {dataset_name}"
        )

        datasets[dataset_name] = (
            load_silver_dataset(
                s3_client,
                dataset_name,
            )
        )

    return datasets


# ---------------------------------------------------------------------
# Gold-Daten speichern
# ---------------------------------------------------------------------

def build_gold_s3_key(
    table_name: str,
) -> str:
    """
    Erzeuge den S3-Objektschlüssel für eine Gold-Tabelle.

    Gold verwendet aktuell genau einen gültigen Snapshot pro Tabelle.
    """
    return (
        f"gold/{table_name}/"
        f"{table_name}.parquet"
    )


def write_gold_table(
    s3_client,
    table_name: str,
    df: pd.DataFrame,
) -> str:
    """
    Serialisiere eine Gold-Tabelle als Parquet und schreibe sie nach S3.

    Ein vorhandenes Objekt mit demselben Schlüssel wird ersetzt. Dadurch gilt
    für Gold eine Snapshot-Semantik: Jede Tabelle repräsentiert den neuesten
    vollständig validierten analytischen Zustand.
    """
    parquet_bytes = dataframe_to_parquet_bytes(
        df
    )

    key = build_gold_s3_key(
        table_name
    )

    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=parquet_bytes,
        ContentType="application/octet-stream",
    )

    return f"s3://{BUCKET_NAME}/{key}"


def write_gold_model(
    s3_client,
    gold_datasets: dict[str, pd.DataFrame],
) -> None:
    """Schreibe alle validierten Gold-Dimensionen und Faktentabellen nach S3."""
    for table_name, df in gold_datasets.items():

        uri = write_gold_table(
            s3_client,
            table_name,
            df,
        )

        print(
            f"Written Gold table: "
            f"{table_name} -> {uri}"
        )


# ---------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------

def main() -> None:
    """Führe die vollständige Silver-to-Gold-Pipeline aus."""
    print("Starting Gold transformation.")

    s3_client = get_s3_client()

    # 1. Validierte Silver-Daten laden.
    silver_datasets = load_all_silver_datasets(
        s3_client
    )

    # 2. Dimensionen und Faktentabellen erzeugen.
    gold_datasets = build_gold_model(
        silver_datasets=silver_datasets,
        config_path=str(SERIES_CONFIG_PATH),
    )

    # 3. Integrität des dimensionalen Modells validieren.
    quality_result = validate_gold_model(
        gold_datasets
    )

    if not quality_result["passed"]:
        raise ValueError(
            "Gold Data Quality validation failed:\n"
            f"{quality_result}"
        )

    print("Gold Data Quality: PASSED")

    # 4. Ausschließlich validierte Gold-Daten persistieren.
    write_gold_model(
        s3_client,
        gold_datasets,
    )

    print("Gold transformation completed successfully.")


if __name__ == "__main__":
    main()