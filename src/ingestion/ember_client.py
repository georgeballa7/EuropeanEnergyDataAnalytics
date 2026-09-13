import os

import requests
from dotenv import load_dotenv

load_dotenv()


class EmberClient:
    BASE_URL = "https://api.ember-energy.org"

    def __init__(self, timeout: int = 30):
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
        Fetch available dates for an Ember dataset.

        This is used as a lightweight check before downloading
        the actual dataset.
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
        """
        Return the latest date currently available from Ember.
        """

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
        Fetch an Ember dataset.

        If start_date is provided, only data beginning from
        that date is requested.
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