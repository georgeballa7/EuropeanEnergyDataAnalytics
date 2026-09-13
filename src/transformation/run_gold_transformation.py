"""
Run the Silver-to-Gold transformation pipeline.

Pipeline
--------
1. Load Silver Parquet datasets from Amazon S3.
2. Build the dimensional Gold model.
3. Validate dimensional-model integrity.
4. Stop immediately if Gold DQ fails.
5. Write validated Gold tables to Amazon S3 as Parquet.

The module is designed to run independently from notebooks and can
later be called by Apache Airflow.
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
# Configuration
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
# AWS session
# ---------------------------------------------------------------------

def get_s3_client():
    """
    Create an S3 client using the local project AWS profile.

    Notes
    -----
    The named profile is appropriate for local development.

    When this code runs inside Airflow in a production AWS environment,
    IAM roles should be preferred over long-lived credentials.
    """
    session = boto3.Session(
        profile_name=AWS_PROFILE,
        region_name=REGION_NAME,
    )

    return session.client("s3")


# ---------------------------------------------------------------------
# Silver loading
# ---------------------------------------------------------------------

def get_latest_silver_key(
    s3_client,
    dataset_name: str,
) -> str:
    """
    Find the most recently written Silver Parquet object.

    Parameters
    ----------
    s3_client:
        Configured boto3 S3 client.

    dataset_name:
        Silver dataset name, for example 'generation'.

    Returns
    -------
    str
        S3 object key of the newest Parquet file.

    Raises
    ------
    FileNotFoundError
        If no Silver Parquet object exists for the dataset.

    Important
    ---------
    The current Silver implementation writes a complete dataset snapshot.
    Therefore the latest object represents the current Silver state.

    If Silver is changed later to append-only incremental files, this
    loading strategy must also be changed.
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
    """
    Load one Silver Parquet dataset from S3 into pandas.
    """
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
    """
    Load all datasets required to construct the Gold model.
    """
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
# Gold storage
# ---------------------------------------------------------------------

def build_gold_s3_key(
    table_name: str,
) -> str:
    """
    Build the S3 key for a Gold table.

    Gold currently uses one current snapshot per table.
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
    Serialize one Gold table as Parquet and write it to S3.

    Existing objects with the same key are replaced. This gives the Gold
    layer snapshot semantics: each table represents the latest validated
    analytical state.
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
    """
    Write every validated Gold dimension and fact table to S3.
    """
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
    """
    Execute the complete Silver-to-Gold pipeline.
    """
    print("Starting Gold transformation.")

    s3_client = get_s3_client()

    # 1. Read validated Silver data.
    silver_datasets = load_all_silver_datasets(
        s3_client
    )

    # 2. Construct dimensions and facts.
    gold_datasets = build_gold_model(
        silver_datasets=silver_datasets,
        config_path=str(SERIES_CONFIG_PATH),
    )

    # 3. Validate dimensional-model integrity.
    quality_result = validate_gold_model(
        gold_datasets
    )

    if not quality_result["passed"]:
        raise ValueError(
            "Gold Data Quality validation failed:\n"
            f"{quality_result}"
        )

    print("Gold Data Quality: PASSED")

    # 4. Persist only validated Gold data.
    write_gold_model(
        s3_client,
        gold_datasets,
    )

    print("Gold transformation completed successfully.")


if __name__ == "__main__":
    main()