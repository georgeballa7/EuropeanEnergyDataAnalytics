"""
Run the Bronze-to-Silver transformation pipeline.

Steps:
1. Load Bronze JSON from S3
2. Transform data
3. Run Data Quality checks
4. Write Silver Parquet to S3
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
    Find the newest Bronze object for a dataset.
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
    Load the latest Bronze JSON file from S3.
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
    Run Bronze-to-Silver processing for one dataset.
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
    s3_client = get_s3_client()

    for dataset_name in DATASETS:
        process_dataset(
            s3_client,
            dataset_name,
        )


if __name__ == "__main__":
    main()