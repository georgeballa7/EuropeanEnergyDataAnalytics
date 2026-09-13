import json
from datetime import datetime, timezone

import boto3


class S3Writer:
    def __init__(
        self,
        bucket_name: str,
        region_name: str = "eu-central-1",
        profile_name: str | None = None,
        bronze_prefix: str = "bronze/ember",
    ):
        self.bucket_name = bucket_name
        self.bronze_prefix = bronze_prefix

        session = boto3.Session(
            profile_name=profile_name,
            region_name=region_name,
        )

        self.s3 = session.client("s3")

    def upload_raw_json(
        self,
        data: dict,
        dataset: str,
    ) -> str:

        now = datetime.now(timezone.utc)

        ingestion_date = now.strftime("%Y-%m-%d")
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")

        key = (
            f"{self.bronze_prefix}/{dataset}/"
            f"ingestion_date={ingestion_date}/"
            f"{dataset}_{timestamp}.json"
        )

        body = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=body,
            ContentType="application/json",
        )

        return f"s3://{self.bucket_name}/{key}"