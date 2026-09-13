"""
Verwalte den persistenten Ladezustand der inkrementellen Ember-Ingestion.

Für jeden Datensatz wird in Amazon S3 unter ``control/ember/`` das zuletzt
erfolgreich geladene Quelldatum gespeichert. Dadurch kann ein späterer Lauf
erkennen, ab welchem Monat neue Daten angefordert werden müssen.

Der Zustand wird erst nach erfolgreichem Schreiben der Bronze-Daten
aktualisiert. Damit wird vermieden, dass die Pipeline Daten als verarbeitet
markiert, obwohl deren Speicherung fehlgeschlagen ist.
"""

import json
import boto3
from botocore.exceptions import ClientError


class IngestionState:
    """Lese und aktualisiere den Ingestion-Zustand eines Datensatzes in S3."""

    def __init__(
        self,
        bucket_name: str,
        region_name: str,
        profile_name: str | None = None,
    ):
        """Initialisiere den S3-Zugriff für die Control-State-Dateien."""
        self.bucket_name = bucket_name

        session = boto3.Session(
            profile_name=profile_name,
            region_name=region_name,
        )

        self.s3 = session.client("s3")

    def _key(self, dataset: str) -> str:
        """Erzeuge den S3-Key der Control-State-Datei eines Datensatzes."""
        return f"control/ember/{dataset}.json"

    def get_last_source_date(self, dataset: str) -> str | None:
        """
        Lese das zuletzt erfolgreich geladene Quelldatum aus S3.

        Existiert für den Datensatz noch keine State-Datei, wird ``None``
        zurückgegeben. Dies signalisiert der Ingestion einen Initial Load.
        Andere AWS-Fehler werden bewusst weitergereicht.
        """
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
        """Speichere das zuletzt erfolgreich geladene Quelldatum in S3."""
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