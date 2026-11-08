"""
Führe die Transformation von Bronze nach Silver aus.

Ablauf
------
1. Liste Bronze-JSON-Inkremente; lade neue Keys anhand des Silver-Manifests.
2. Bereinige und typisiere die Bronze-Daten für die Silver-Schicht.
3. Lade den aktuellen Silver-Snapshot, sofern bereits einer existiert.
4. Führe bestehenden Snapshot und Bronze-Daten anhand des fachlichen Grains zusammen.
5. Führe die definierten Data-Quality-Prüfungen auf dem vollständigen Zustand aus.
6. Schreibe ausschließlich validierte Silver-Daten als Parquet nach S3.

Silver verwendet damit eine Snapshot-Semantik: Bronze bleibt append-only und
quellnah, während der jeweils neueste Silver-Snapshot den vollständigen,
bereinigten und deduplizierten Zustand eines Datensatzes repräsentiert.

Ein Manifest bindet die verarbeiteten Bronze-Keys an den geschriebenen Silver-
Snapshot (ETag). Bei fehlendem oder inkonsistentem Manifest und bei geänderten
oder entfernten Bronze-Objekten erfolgt ein vollständiger Wiederaufbau. Ein
fehlgeschlagener Silver-Lauf aktualisiert das Manifest nicht.
"""

import io
import json

import boto3
import pandas as pd

from config.settings import get_aws_settings, load_config
from src.quality.data_quality import validate_dataset
from src.transformation.clean_energy_data import clean_energy_data
from src.transformation.silver_writer import build_silver_s3_key, write_silver_to_s3
from src.transformation.silver_checkpoint import choose_bronze_keys, save_silver_manifest
from src.utils.s3_listing import latest_object_key

BUCKET_NAME, REGION_NAME = get_aws_settings()
DATASETS = ["generation", "demand", "emissions", "carbon_intensity", "capacity"]
BUSINESS_KEYS = {
    "generation": ["entity_code", "date", "series"],
    "demand": ["entity_code", "date"],
    "emissions": ["entity_code", "date", "series"],
    "carbon_intensity": ["entity_code", "date"],
    "capacity": ["entity_code", "date", "series"],
}


def get_s3_client():
    """
    Erzeuge einen S3-Client über die boto3-Credential-Provider-Chain.

    AWS_PROFILE kann lokal gesetzt werden; in AWS werden IAM-Rollen genutzt.
    """
    session = boto3.Session(region_name=REGION_NAME)
    return session.client("s3")


def get_expected_countries(dataset_name: str) -> list[str]:
    """Lade den erwarteten Länderscope eines Datensatzes aus der YAML-Konfiguration."""
    config = load_config()
    return config["datasets"][dataset_name].get("countries", config["countries"])


def get_bronze_objects(s3_client, dataset_name: str) -> list[dict]:
    """
    Ermittle alle vorhandenen Bronze-JSON-Objekte eines Datensatzes.

    Die Objekte werden chronologisch nach ``LastModified`` sortiert. Dadurch
    werden ältere Inkremente vor neueren verarbeitet und spätere Werte können
    bei identischen Business Keys deterministisch den vorherigen Stand
    ersetzen.

    Raises
    ------
    FileNotFoundError
        Wenn für den Datensatz kein Bronze-JSON-Objekt vorhanden ist.
    """
    prefix = f"bronze/ember/{dataset_name}/"
    json_objects = []
    continuation_token = None

    while True:
        request = {
            "Bucket": BUCKET_NAME,
            "Prefix": prefix,
        }
        if continuation_token is not None:
            request["ContinuationToken"] = continuation_token

        response = s3_client.list_objects_v2(**request)
        json_objects.extend(
            obj for obj in response.get("Contents", []) if obj["Key"].endswith(".json")
        )

        if not response.get("IsTruncated"):
            break
        continuation_token = response["NextContinuationToken"]

    if not json_objects:
        raise FileNotFoundError(
            f"Kein Bronze-JSON für den Datensatz '{dataset_name}' gefunden."
        )

    return sorted(json_objects, key=lambda obj: (obj["LastModified"], obj["Key"]))


def get_bronze_keys(s3_client, dataset_name: str) -> list[str]:
    """Kompatible öffentliche Hilfsfunktion zum Auflisten aller Bronze-Keys."""
    return [obj["Key"] for obj in get_bronze_objects(s3_client, dataset_name)]


def load_bronze_dataframes(
    s3_client, dataset_name: str, keys: list[str] | None = None
) -> list[pd.DataFrame]:
    """Lade nur die ausgewählten Bronze-JSON-Inkremente aus S3."""
    if keys is None:
        keys = get_bronze_keys(s3_client, dataset_name)
    dataframes = []
    for key in keys:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        payload = json.loads(response["Body"].read().decode("utf-8"))
        dataframes.append(pd.DataFrame(payload["data"]))
    return dataframes


def merge_silver_snapshot(
    current_silver_df: pd.DataFrame | None,
    new_silver_df: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """Führe bestehenden Silver-Snapshot und neue bereinigte Daten zusammen."""
    if current_silver_df is None:
        combined_df = new_silver_df.copy()
    else:
        combined_df = pd.concat([current_silver_df, new_silver_df], ignore_index=True)

    business_key = BUSINESS_KEYS[dataset_name]
    return (
        combined_df.drop_duplicates(subset=business_key, keep="last")
        .sort_values(business_key)
        .reset_index(drop=True)
    )


def process_dataset(s3_client, dataset_name: str) -> None:
    """Lade neue Bronze-Objekte oder rekonstruiere Silver bei Abweichungen."""
    print(f"Verarbeite Datensatz: {dataset_name}")
    bronze_objects = get_bronze_objects(s3_client, dataset_name)
    silver_key = get_latest_silver_key(s3_client, dataset_name)
    pending_keys, full_rebuild = choose_bronze_keys(
        s3_client, BUCKET_NAME, dataset_name, bronze_objects, silver_key
    )
    if not pending_keys:
        print(f"Keine neuen Bronze-Objekte für {dataset_name}; Silver unverändert.")
        return

    bronze_dataframes = load_bronze_dataframes(s3_client, dataset_name, pending_keys)
    cleaned_dataframes = [
        clean_energy_data(bronze_df, dataset_name)
        for bronze_df in bronze_dataframes
    ]
    new_silver_df = pd.concat(cleaned_dataframes, ignore_index=True)

    # A stale or missing manifest makes the existing Silver snapshot unsafe as
    # a merge base. Rebuild exclusively from immutable Bronze history instead.
    current_silver_df = None if full_rebuild else load_latest_silver_dataframe(
        s3_client, dataset_name
    )
    silver_df = merge_silver_snapshot(
        current_silver_df=current_silver_df,
        new_silver_df=new_silver_df,
        dataset_name=dataset_name,
    )
    quality_result = validate_dataset(
        silver_df,
        dataset_name,
        get_expected_countries(dataset_name),
    )
    if not quality_result["passed"]:
        raise ValueError(
            f"DQ-Validierung für '{dataset_name}' fehlgeschlagen: {quality_result}"
        )

    s3_uri = write_silver_to_s3(
        df=silver_df,
        dataset_name=dataset_name,
        bucket_name=BUCKET_NAME,
        region_name=REGION_NAME,
    )
    # Publish the checkpoint ONLY after the validated snapshot was persisted.
    snapshot_key = build_silver_s3_key(dataset_name)
    snapshot_etag = s3_client.head_object(
        Bucket=BUCKET_NAME, Key=snapshot_key
    )["ETag"]
    save_silver_manifest(
        s3_client, BUCKET_NAME, dataset_name, bronze_objects,
        snapshot_key, snapshot_etag
    )
    print(f"Abgeschlossen: {dataset_name} -> {s3_uri}")

def main() -> None:
    """Führe die Bronze-zu-Silver-Verarbeitung für alle Projektdatensätze aus."""
    s3_client = get_s3_client()
    for dataset_name in DATASETS:
        process_dataset(s3_client, dataset_name)


if __name__ == "__main__":
    main()
