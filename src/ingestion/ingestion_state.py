import json
import boto3
from botocore.exceptions import ClientError


class IngestionState:
    def __init__(
        self,
        bucket_name: str,
        region_name: str,
        profile_name: str | None = None,
    ):
        self.bucket_name = bucket_name

        session = boto3.Session(
            profile_name=profile_name,
            region_name=region_name,
        )

        self.s3 = session.client("s3")

    def _key(self, dataset: str) -> str:
        return f"control/ember/{dataset}.json"

    def get_last_source_date(self, dataset: str) -> str | None:
        try:
            response = self.s3.get_object(
                Bucket=self.bucket_name,
                Key=self._key(dataset),
            )

            state = json.loads(
                response["Body"].read().decode("utf-8")
            )

            return state.get("last_source_date")

        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def update(
        self,
        dataset: str,
        last_source_date: str,
    ) -> None:

        body = json.dumps(
            {
                "dataset": dataset,
                "last_source_date": last_source_date,
            }
        ).encode("utf-8")

        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=self._key(dataset),
            Body=body,
            ContentType="application/json",
        )