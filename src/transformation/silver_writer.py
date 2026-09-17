"""
Schreibe DataFrames der Silver-Schicht als Parquet-Dateien nach Amazon S3.

Das Modul trennt die fachliche Transformation bewusst von der Speicherung.
Es serialisiert bereits bereinigte und validierte Silver-Daten in das
spaltenorientierte Parquet-Format und legt sie anschließend in S3 ab.
"""

from __future__ import annotations

import io

import boto3
import pandas as pd


def dataframe_to_parquet_bytes(
    df: pd.DataFrame,
) -> bytes:
    """
    Serialisiere einen pandas DataFrame im Arbeitsspeicher als Parquet.

    Rückgabe
    --------
    bytes
        Binärer Inhalt der erzeugten Parquet-Datei.
    """
    buffer = io.BytesIO()

    df.to_parquet(
        buffer,
        index=False,
        engine="pyarrow",
    )

    buffer.seek(0)

    return buffer.getvalue()


def build_silver_s3_key(
    dataset_name: str,
) -> str:
    """
    Erzeuge den S3-Objektschlüssel für einen Silver-Datensatz.

    Silver verwendet einen stabilen Objektschlüssel. Nach erfolgreicher
    Validierung ersetzt jeder Lauf den bisherigen vollständigen Snapshot.
    """
    return (
        f"silver/ember/{dataset_name}/"
        f"{dataset_name}.parquet"
    )


def write_silver_to_s3(
    df: pd.DataFrame,
    dataset_name: str,
    bucket_name: str,
    aws_profile: str | None = None,
    region_name: str = "eu-central-1",
) -> str:
    """
    Serialisiere einen Silver-DataFrame als Parquet und lade ihn nach S3.

    Parameter
    ---------
    df:
        Bereinigter und für die Silver-Schicht vorbereiteter DataFrame.

    dataset_name:
        Name des Ember-Datensatzes.

    bucket_name:
        Ziel-Bucket in Amazon S3.

    aws_profile:
        Optionales lokales AWS-CLI-Profil. In einer produktiven AWS-Umgebung
        sollten IAM Roles und temporäre Credentials bevorzugt werden.

    region_name:
        AWS-Region des Projekts.

    Rückgabe
    --------
    str
        Vollständige S3-URI des hochgeladenen Parquet-Objekts.
    """
    parquet_bytes = dataframe_to_parquet_bytes(df)

    s3_key = build_silver_s3_key(
        dataset_name
    )

    if aws_profile:
        session = boto3.Session(
            profile_name=aws_profile,
            region_name=region_name,
        )
    else:
        session = boto3.Session(
            region_name=region_name,
        )

    s3_client = session.client("s3")

    s3_client.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=parquet_bytes,
        ContentType="application/octet-stream",
    )

    return f"s3://{bucket_name}/{s3_key}"