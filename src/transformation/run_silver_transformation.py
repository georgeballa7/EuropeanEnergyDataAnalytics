"""
Führe die Transformation von Bronze nach Silver aus.

Ablauf
------
1. Lade das neueste Bronze-JSON-Inkrement aus Amazon S3.
2. Bereinige und typisiere die neuen Daten für die Silver-Schicht.
3. Lade den aktuellen Silver-Snapshot, sofern bereits einer existiert.
4. Führe bestehenden Snapshot und neue Daten anhand des fachlichen Grains zusammen.
5. Führe die definierten Data-Quality-Prüfungen auf dem vollständigen Zustand aus.
6. Schreibe ausschließlich validierte Silver-Daten als Parquet nach S3.

Silver verwendet damit eine Snapshot-Semantik: Bronze bleibt append-only und
quellnah, während der jeweils neueste Silver-Snapshot den vollständigen,
bereinigten und deduplizierten Zustand eines Datensatzes repräsentiert.
"""

import io
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

BUSINESS_KEYS = {
    "generation": ["entity_code", "date", "series"],
    "demand": ["entity_code", "date"],
    "emissions": ["entity_code", "date", "series"],
    "carbon_intensity": ["entity_code", "date"],
    "capacity": ["entity_code", "date", "series"],
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


def get_latest_silver_key(
    s3_client,
    dataset_name: str,
) -> str | None:
    """Ermittle den neuesten vorhandenen Silver-Snapshot eines Datensatzes."""
    prefix = f"silver/ember/{dataset_name}/"

    response = s3_client.list_objects_v2(
        Bucket=BUCKET_NAME,
        Prefix=prefix,
    )

    parquet_objects = [
        obj
        for obj in response.get("Contents", [])
        if obj["Key"].endswith(".parquet")
    ]

    if not parquet_objects:
        return None

    latest_object = max(
        parquet_objects,
        key=lambda obj: obj["LastModified"],
    )

    return latest_object["Key"]


def load_latest_silver_dataframe(
    s3_client,
    dataset_name: str,
) -> pd.DataFrame | None:
    """Lade den aktuellen Silver-Snapshot, sofern bereits einer existiert."""
    key = get_latest_silver_key(
        s3_client,
        dataset_name,
    )

    if key is None:
        return None

    response = s3_client.get_object(
        Bucket=BUCKET_NAME,
        Key=key,
    )

    return pd.read_parquet(
        io.BytesIO(response["Body"].read()),
        engine="pyarrow",
    )


def merge_silver_snapshot(
    current_silver_df: pd.DataFrame | None,
    new_silver_df: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Führe bestehenden Silver-Snapshot und neue bereinigte Daten zusammen.

    Der fachliche Schlüssel hängt vom Datensatz ab. Bei Überschneidungen
    gewinnt die neu geladene Version, sodass wiederholte Verarbeitung keine
    Duplikate im vollständigen Silver-Snapshot erzeugt.
    """
    if current_silver_df is None:
        combined_df = new_silver_df.copy()
    else:
        combined_df = pd.concat(
            [current_silver_df, new_silver_df],
            ignore_index=True,
        )

    business_key = BUSINESS_KEYS[dataset_name]

    combined_df = (
        combined_df
        .drop_duplicates(
            subset=business_key,
            keep="last",
        )
        .sort_values(business_key)
        .reset_index(drop=True)
    )

    return combined_df


def process_dataset(
    s3_client,
    dataset_name: str,
) -> None:
    """
    Verarbeite einen Datensatz vollständig von Bronze nach Silver.

    Die Funktion bereinigt das neueste Bronze-Inkrement, führt es mit dem
    bestehenden Silver-Snapshot zusammen, validiert den vollständigen neuen
    Zustand und schreibt ihn nur bei erfolgreicher Data-Quality-Prüfung nach S3.
    """
    print(f"Processing: {dataset_name}")

    bronze_df = load_bronze_dataframe(
        s3_client,
        dataset_name,
    )

    new_silver_df = clean_energy_data(
        bronze_df,
        dataset_name,
    )

    current_silver_df = load_latest_silver_dataframe(
        s3_client,
        dataset_name,
    )

    silver_df = merge_silver_snapshot(
        current_silver_df=current_silver_df,
        new_silver_df=new_silver_df,
        dataset_name=dataset_name,
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
