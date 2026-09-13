"""
Write Silver-layer DataFrames to Amazon S3 as Parquet files.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import boto3
import pandas as pd


def dataframe_to_parquet_bytes(
    df: pd.DataFrame,
) -> bytes:
    """
    Serialize a pandas DataFrame to Parquet in memory.

    Returns
    -------
    bytes
        Parquet file content.
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
    Build the S3 object key for a Silver dataset.
    """
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    return (
        f"silver/ember/{dataset_name}/"
        f"{dataset_name}_{timestamp}.parquet"
    )


def write_silver_to_s3(
    df: pd.DataFrame,
    dataset_name: str,
    bucket_name: str,
    aws_profile: str | None = None,
    region_name: str = "eu-central-1",
) -> str:
    """
    Serialize a Silver DataFrame as Parquet and upload it to S3.

    Parameters
    ----------
    df:
        Silver-ready DataFrame.

    dataset_name:
        Name of the Ember dataset.

    bucket_name:
        Target S3 bucket.

    aws_profile:
        Optional local AWS CLI profile.
        In production, IAM roles should be preferred.

    region_name:
        AWS region.

    Returns
    -------
    str
        Full S3 URI of the uploaded Parquet object.
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