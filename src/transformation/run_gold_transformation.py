"""
Führe die Transformation von Silver nach Gold aus.

Pipeline
--------
1. Lade die Silver-Parquet-Datensätze aus Amazon S3.
2. Erzeuge das dimensionale Gold-Modell.
3. Validiere die Integrität des dimensionalen Modells.
4. Brich die Verarbeitung sofort ab, wenn die Gold-DQ fehlschlägt.
5. Schreibe validierte Tabellen als versionierte Parquet-Snapshots nach S3.
6. Veröffentliche alle neun Glue-Tabellen mit best-effort Rollback bei Fehlern.
"""

from __future__ import annotations

import copy
import io
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import boto3
import pandas as pd

from config.settings import get_aws_settings
from src.catalog.glue_catalog import (
    DATABASE_NAME, GOLD_TABLE_SCHEMAS, build_table_input, get_glue_client,
)
from src.quality.gold_quality import validate_gold_model
from src.transformation.build_gold_model import build_gold_model
from src.transformation.silver_writer import dataframe_to_parquet_bytes
from src.utils.s3_listing import latest_object_key

BUCKET_NAME, REGION_NAME = get_aws_settings()
SILVER_DATASETS = ["generation", "demand", "emissions", "carbon_intensity", "capacity"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERIES_CONFIG_PATH = PROJECT_ROOT / "config" / "series_config.yaml"


def get_s3_client():
    """Erzeuge einen S3-Client über die boto3-Credential-Provider-Chain."""
    session = boto3.Session(region_name=REGION_NAME)
    return session.client("s3")


def get_latest_silver_key(s3_client, dataset_name: str) -> str:
    """Ermittle das zuletzt geschriebene Silver-Parquet-Objekt."""
    prefix = f"silver/ember/{dataset_name}/"
    key = latest_object_key(s3_client, BUCKET_NAME, prefix, ".parquet")
    if key is None:
        raise FileNotFoundError(
            f"Keine Silver-Parquet-Datei für den Datensatz '{dataset_name}' gefunden."
        )
    return key


def load_silver_dataset(s3_client, dataset_name: str) -> pd.DataFrame:
    """Lade einen Silver-Parquet-Datensatz aus S3 in einen pandas DataFrame."""
    key = get_latest_silver_key(s3_client, dataset_name)
    response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
    return pd.read_parquet(
        io.BytesIO(response["Body"].read()),
        engine="pyarrow",
    )


def load_all_silver_datasets(s3_client) -> dict[str, pd.DataFrame]:
    """Lade alle Silver-Datensätze, die für das Gold-Modell benötigt werden."""
    datasets = {}
    for dataset_name in SILVER_DATASETS:
        print(f"Lade Silver-Datensatz: {dataset_name}")
        datasets[dataset_name] = load_silver_dataset(s3_client, dataset_name)
    return datasets


def build_gold_s3_key(table_name: str, snapshot_id: str) -> str:
    """Versionierten, unveränderlichen Key einer Gold-Tabelle erzeugen."""
    return f"gold/{table_name}/snapshots/{snapshot_id}/{table_name}.parquet"


def write_gold_table(
    s3_client, table_name: str, df: pd.DataFrame, snapshot_id: str
) -> str:
    """Gold-Parquet schreiben, ohne das bisher veröffentlichte Objekt zu ersetzen."""
    parquet_bytes = dataframe_to_parquet_bytes(df)
    key = build_gold_s3_key(table_name, snapshot_id)
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=parquet_bytes,
        ContentType="application/octet-stream",
    )
    return f"s3://{BUCKET_NAME}/{key}"


def _existing_gold_table(glue_client, table_name: str) -> dict | None:
    try:
        return glue_client.get_table(
            DatabaseName=DATABASE_NAME, Name=table_name
        )["Table"]
    except glue_client.exceptions.EntityNotFoundException:
        return None


def _restore_table_input(previous: dict) -> dict:
    """Nur zulässige Glue TableInput-Felder eines Backups wiederherstellen."""
    allowed = {
        "Name", "Description", "Owner", "LastAccessTime", "LastAnalyzedTime",
        "Retention", "StorageDescriptor", "PartitionKeys", "ViewOriginalText",
        "ViewExpandedText", "TableType", "Parameters", "TargetTable",
        "ViewDefinition",
    }
    return {key: copy.deepcopy(value) for key, value in previous.items()
            if key in allowed}


def _restore_gold_table(glue_client, table_name: str, previous: dict | None) -> None:
    current = _existing_gold_table(glue_client, table_name)
    if previous is None:
        if current is not None:
            glue_client.delete_table(DatabaseName=DATABASE_NAME, Name=table_name)
    elif current is None:
        glue_client.create_table(
            DatabaseName=DATABASE_NAME, TableInput=_restore_table_input(previous)
        )
    else:
        glue_client.update_table(
            DatabaseName=DATABASE_NAME, TableInput=_restore_table_input(previous)
        )


def write_gold_model(
    s3_client,
    gold_datasets: dict[str, pd.DataFrame],
    glue_client=None,
    snapshot_id: str | None = None,
) -> list[str]:
    """Neun Tabellen zuerst vollständig nach S3 schreiben, danach Glue umstellen.

    Die neun Glue-Updates sind NICHT atomar. Falls eines scheitert, wird
    best-effort in umgekehrter Reihenfolge auf die alten Definitionen
    zurückgestellt. Alte Snapshots bleiben unverändert und referenzierbar.
    """
    if set(gold_datasets) != set(GOLD_TABLE_SCHEMAS):
        raise ValueError("Core Gold model must contain all nine registered tables")
    glue_client = glue_client or get_glue_client()
    snapshot_id = snapshot_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-" + uuid4().hex[:8]
    )
    previous = {
        table_name: _existing_gold_table(glue_client, table_name)
        for table_name in GOLD_TABLE_SCHEMAS
    }

    # Stage every table before publishing the first Glue definition.
    staged = {}
    for table_name, df in gold_datasets.items():
        staged[table_name] = write_gold_table(
            s3_client, table_name, df, snapshot_id
        )
    touched = []
    try:
        for table_name in GOLD_TABLE_SCHEMAS:
            input_definition = build_table_input(
                table_name, GOLD_TABLE_SCHEMAS[table_name],
                f"s3://{BUCKET_NAME}/gold/{table_name}/snapshots/{snapshot_id}/",
            )
            input_definition["Parameters"]["core_gold_snapshot_id"] = snapshot_id
            touched.append(table_name)  # include failing operation in rollback
            args = {"DatabaseName": DATABASE_NAME, "TableInput": input_definition}
            if previous[table_name] is None:
                glue_client.create_table(**args)
            else:
                glue_client.update_table(**args)
    except Exception as exc:
        rollback_errors = []
        for table_name in reversed(touched):
            try:
                _restore_gold_table(glue_client, table_name, previous[table_name])
            except Exception as rollback_exc:
                rollback_errors.append(f"{table_name}: {rollback_exc}")
        if rollback_errors:
            raise RuntimeError(
                f"Core Gold publication failed ({exc}); rollback incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    # Do not delete old or orphaned snapshots; cleanup requires a review.
    return [staged[table_name] for table_name in GOLD_TABLE_SCHEMAS]

def main() -> None:
    """Führe die vollständige Silver-zu-Gold-Pipeline aus."""
    print("Starte Gold-Transformation.")
    s3_client = get_s3_client()
    silver_datasets = load_all_silver_datasets(s3_client)
    gold_datasets = build_gold_model(
        silver_datasets=silver_datasets,
        config_path=str(SERIES_CONFIG_PATH),
    )
    quality_result = validate_gold_model(gold_datasets)

    if not quality_result["passed"]:
        raise ValueError(
            "Gold-Datenqualitätsprüfung fehlgeschlagen:\n"
            f"{quality_result}"
        )

    print("Gold-Datenqualität: BESTANDEN")
    published = write_gold_model(s3_client, gold_datasets)
    for uri in published:
        print(f"Core Gold snapshot veröffentlicht: {uri}")
    print("Gold-Transformation erfolgreich abgeschlossen.")


if __name__ == "__main__":
    main()
