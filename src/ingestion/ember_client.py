"""
Client für den Zugriff auf die Ember Energy API.

Das Modul kapselt die HTTP-Kommunikation mit Ember und stellt gezielte
Methoden für verfügbare Quelldaten sowie den eigentlichen Datendownload
bereit. Der API-Schlüssel wird aus der Umgebungsvariable ``EMBER_API_KEY``
gelesen und nicht im Quellcode gespeichert.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


class EmberClient:
    """Kapsle wiederverwendbare Zugriffe auf die Ember Energy API."""

    BASE_URL = "https://api.ember-energy.org"

    def __init__(self, timeout: int = 30):
        """Initialisiere den Client mit API-Schlüssel und Request-Timeout."""
        self.api_key = os.getenv("EMBER_API_KEY")
        self.timeout = timeout

        if not self.api_key:
            raise ValueError(
                "EMBER_API_KEY was not found in the environment."
            )

    def get_available_dates(
        self,
        dataset: str,
        temporal_resolution: str = "monthly",
    ) -> dict:
        """
        Lade die verfügbaren Datumswerte für einen Ember-Datensatz.

        Diese leichte Options-Abfrage wird verwendet, bevor der eigentliche
        Datensatz geladen wird. Dadurch kann die Pipeline zunächst prüfen, ob
        überhaupt neue Quelldaten vorhanden sind.
        """
        endpoint = (
            f"/v1/options/"
            f"{dataset}/"
            f"{temporal_resolution}/date"
        )

        response = requests.get(
            f"{self.BASE_URL}{endpoint}",
            params={"api_key": self.api_key},
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.json()

    def get_latest_available_date(
        self,
        dataset: str,
        temporal_resolution: str = "monthly",
    ) -> str:
        """Gib das aktuell neueste bei Ember verfügbare Quelldatum zurück."""
        result = self.get_available_dates(
            dataset=dataset,
            temporal_resolution=temporal_resolution,
        )

        latest_date = (
            result
            .get("stats", {})
            .get("user_data_range", {})
            .get("max")
        )

        if latest_date is None:
            raise ValueError(
                f"No latest available date found for {dataset}"
            )

        return latest_date

    def fetch_dataset(
        self,
        endpoint: str,
        countries: list[str],
        start_date: str | None = None,
    ) -> dict:
        """
        Lade einen Ember-Datensatz für die angegebenen Länder.

        Wird ``start_date`` übergeben, fordert die API nur Daten ab diesem
        Zeitpunkt an. Dadurch unterstützt die Methode inkrementelle Loads,
        ohne historische Daten unnötig erneut herunterzuladen.
        """
        params = {
            "entity_code": ",".join(countries),
            "api_key": self.api_key,
        }

        if start_date is not None:
            params["start_date"] = start_date

        response = requests.get(
            f"{self.BASE_URL}{endpoint}",
            params=params,
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.json()