"""
Schreibe rohe Ember-API-Antworten in die Bronze-Schicht von Amazon S3.

Die Bronze-Schicht bewahrt die API-Antwort möglichst quellnah als JSON auf.
Die Objekte werden nach Datensatz und Ingestion-Datum organisiert und erhalten
einen UTC-Zeitstempel, sodass einzelne Ladevorgänge nachvollziehbar bleiben.
"""

import json
from datetime import datetime, timezone

import boto3


class S3Writer:
    """Kapsle das Schreiben unveränderter Bronze-JSON-Objekte nach S3."""

    def __init__(
        self,
        bucket_name: str,
        region_name: str = "eu-central-1",
        profile_name: str | None = None,
        bronze_prefix: str = "bronze/ember",
    ):
        """Initialisiere Bucket, Bronze-Präfix und S3-Client."""
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
        """
        Speichere eine vollständige Ember-API-Antwort als Bronze-JSON in S3.

        Der S3-Key folgt dem Muster
        ``bronze/ember/<dataset>/ingestion_date=YYYY-MM-DD/<dataset>_<timestamp>.json``.
        Dadurch bleibt sowohl der Datensatz als auch der Zeitpunkt der
        Ingestion im Speicherpfad nachvollziehbar.

        Rückgabe
        --------
        str
            Vollständige S3-URI des geschriebenen Bronze-Objekts.
        """
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