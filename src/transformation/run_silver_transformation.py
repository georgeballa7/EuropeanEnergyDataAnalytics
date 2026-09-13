"""
Führe die Transformation von Bronze nach Silver aus.

Ablauf
------
1. Lade die aktuelle Bronze-JSON-Datei aus Amazon S3.
2. Bereinige und typisiere die Daten für die Silver-Schicht.
3. Führe die definierten Data-Quality-Prüfungen aus.
4. Schreibe ausschließlich validierte Silver-Daten als Parquet nach S3.

Wichtiger aktueller Stand
-------------------------
Die Funktion lädt derzeit nur das zuletzt geschriebene Bronze-Objekt je
Datensatz. Das ist korrekt, solange dieses Objekt einen vollständigen Snapshot
enthält. Sobald Bronze echte append-only inkrementelle Dateien enthält, muss
diese Ladestrategie erweitert werden, damit alle relevanten Objekte verarbeitet
bzw. zu einem konsistenten Silver-Zustand zusammengeführt werden.
"""

import json

import boto3
import pandas as pd

from src.transformation.clean_energy_data import clean_energy_data
from src.transformation.silver_writer import write_silver_to_s3
from src.quality.data_quality import validate_dataset


BUCKET_NAME = "european-energy-data-analytics-488658242500-eu-central-1-an"
AWS_PROFILE = "energy-pipeline"
REGION_NAME = "eu-central-1"

DATASETS = [
    "generation",
    "demand",
    "emissions",
    "carbon_intensity",
    "capacity",
]

EXPECTED_COUNTRIES = {
    "DEU", "FRA", "ESP", "ITA", "GBR",
    "NLD", "BEL", "AUT", "POL", "CZE",
    "DNK", "SWE", "NOR", "FIN", "PRT",
    "IRL", "GRC", "ROU", "HUN", "CHE",
}


def get_s3_client():
    """
    Erzeuge einen S3-Client mit dem lokalen AWS-Profil des Projekts.

    Das benannte Profil ist für die lokale Entwicklung vorgesehen. In einer
    produktiven AWS-Umgebung sollten IAM Roles und temporäre Credentials
    bevorzugt werden.
    """
    session = boto3.Session(
        profile_name=AWS_PROFILE,
        region_name=REGION_NAME,
    )

    return session.client("s3")


def get_latest_bronze_key(
    s3_client,
    dataset_name: str,
) -> str:
    """
    Ermittle das zuletzt geschriebene Bronze-JSON-Objekt eines Datensatzes.

    Rückgabe
    --------
    str
        S3-Objektschlüssel der neuesten JSON-Datei.

    Raises
    ------
    FileNotFoundError
        Wenn für den Datensatz kein Bronze-JSON-Objekt vorhanden ist.
    """
    prefix = f"bronze/ember/{dataset_name}/"

    response = s3_client.list_objects_v2(
        Bucket=BUCKET_NAME,
        Prefix=prefix,
    )

    objects = response.get("Contents", [])

    json_objects = [
        obj
        for obj in objects
        if obj["Key"].endswith(".json")
    ]

    if not json_objects:
        raise FileNotFoundError(
            f"No Bronze JSON found for dataset: {dataset_name}"
        )

    latest_object = max(
        json_objects,
        key=lambda obj: obj["LastModified"],
    )

    return latest_object["Key"]


def load_bronze_dataframe(
    s3_client,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Lade das neueste Bronze-JSON-Objekt aus S3 in einen pandas DataFrame.

    Die vollständige Bronze-Datei enthält weiterhin die originale API-Antwort.
    Für die Silver-Transformation wird daraus ausschließlich der Bereich
    ``data`` in einen tabellarischen DataFrame überführt.
    """
    key = get_latest_bronze_key(
        s3_client,
        dataset_name,
    )

    response = s3_client.get_object(
        Bucket=BUCKET_NAME,
        Key=key,
    )

    payload = json.loads(
        response["Body"].read().decode("utf-8")
    )

    return pd.DataFrame(
        payload["data"]
    )


def process_dataset(
    s3_client,
    dataset_name: str,
) -> None:
    """
    Verarbeite einen Datensatz vollständig von Bronze nach Silver.

    Die Funktion lädt die Bronze-Daten, wendet die fachlichen
    Transformationsregeln an, führt die Data-Quality-Prüfung aus und schreibt
    das Ergebnis nur bei erfolgreicher Validierung nach S3.
    """
    print(f"Processing: {dataset_name}")

    bronze_df = load_bronze_dataframe(
        s3_client,
        dataset_name,
    )

    silver_df = clean_energy_data(
        bronze_df,
        dataset_name,
    )

    quality_result = validate_dataset(
        silver_df,
        dataset_name,
        EXPECTED_COUNTRIES,
    )

    if not quality_result["passed"]:
        raise ValueError(
            f"DQ validation failed for {dataset_name}: "
            f"{quality_result}"
        )

    s3_uri = write_silver_to_s3(
        df=silver_df,
        dataset_name=dataset_name,
        bucket_name=BUCKET_NAME,
        aws_profile=AWS_PROFILE,
        region_name=REGION_NAME,
    )

    print(
        f"Completed: {dataset_name} -> {s3_uri}"
    )


def main():
    """Führe die Bronze-to-Silver-Verarbeitung für alle Projektdatensätze aus."""
    s3_client = get_s3_client()

    for dataset_name in DATASETS:
        process_dataset(
            s3_client,
            dataset_name,
        )


if __name__ == "__main__":
    main()