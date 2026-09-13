import logging
from datetime import date, datetime

from config.settings import load_config
from src.ingestion.ember_client import EmberClient
from src.ingestion.ingestion_state import IngestionState
from src.ingestion.s3_writer import S3Writer


logger = logging.getLogger(__name__)


def parse_date(value: str) -> date:
    """
    Convert Ember/state ISO date strings to a Python date.

    Examples:
        2026-08-01
        2026-08-01T00:00:00
        2026-08-01T00:00:00Z
    """
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).date()


def next_month(value: date) -> date:
    """
    Return the first day of the month following value.
    """
    if value.month == 12:
        return date(
            year=value.year + 1,
            month=1,
            day=1,
        )

    return date(
        year=value.year,
        month=value.month + 1,
        day=1,
    )


def normalize_project_start_date(value: str) -> date:
    """
    Convert config values such as '2015-01'
    to '2015-01-01'.
    """
    if len(value) == 7:
        value = f"{value}-01"

    return date.fromisoformat(value)


def run_ingestion() -> None:
    config = load_config()

    countries = config["countries"]
    datasets = config["datasets"]

    project_start_date = normalize_project_start_date(
        config["source"]["start_date"]
    )

    client = EmberClient()

    writer = S3Writer(
        bucket_name=config["project"]["bucket"],
        region_name=config["project"]["region"],
        profile_name=config["aws"].get("profile_name"),
        bronze_prefix=config["storage"]["bronze_prefix"],
    )

    state = IngestionState(
        bucket_name=config["project"]["bucket"],
        region_name=config["project"]["region"],
        profile_name=config["aws"].get("profile_name"),
    )

    checked = 0
    updated = 0
    skipped = 0

    logger.info("Starting Ember incremental ingestion")

    for dataset_name, dataset_config in datasets.items():
        checked += 1

        endpoint = dataset_config["endpoint"]
        api_dataset = dataset_config["api_dataset"]

        logger.info(
            "Checking dataset: %s",
            dataset_name,
        )

        # --------------------------------------------------
        # 1. Lightweight check against Ember Options API
        # --------------------------------------------------

        latest_available_raw = (
            client.get_latest_available_date(
                dataset=api_dataset,
                temporal_resolution="monthly",
            )
        )

        latest_available = parse_date(
            latest_available_raw
        )

        # --------------------------------------------------
        # 2. Read ingestion state from S3
        # --------------------------------------------------

        last_loaded_raw = state.get_last_source_date(
            dataset_name
        )

        last_loaded = (
            parse_date(last_loaded_raw)
            if last_loaded_raw
            else None
        )

        logger.info(
            "%s | last_loaded=%s | latest_available=%s",
            dataset_name,
            last_loaded,
            latest_available,
        )

        # --------------------------------------------------
        # 3. Nothing new -> skip large dataset API request
        # --------------------------------------------------

        if (
            last_loaded is not None
            and latest_available <= last_loaded
        ):
            logger.info(
                "Skipping %s: no new data available.",
                dataset_name,
            )

            skipped += 1
            continue

        # --------------------------------------------------
        # 4. Determine incremental starting point
        # --------------------------------------------------

        if last_loaded is None:
            incremental_start = project_start_date

            logger.info(
                "%s | No previous state found. "
                "Starting initial load from %s.",
                dataset_name,
                incremental_start,
            )

        else:
            incremental_start = next_month(
                last_loaded
            )

            logger.info(
                "%s | New data detected. Loading from %s.",
                dataset_name,
                incremental_start,
            )

        # --------------------------------------------------
        # 5. Download only new data
        # --------------------------------------------------

        response = client.fetch_dataset(
            endpoint=endpoint,
            countries=countries,
            start_date=incremental_start.isoformat(),
        )

        data = response.get("data", [])

        if not data:
            logger.warning(
                "%s | API returned no records. "
                "State will not be changed.",
                dataset_name,
            )

            skipped += 1
            continue

        stats = response.get("stats", {})

        actual_latest_raw = (
            stats
            .get("query_value_range", {})
            .get("date", {})
            .get("max")
        )

        if actual_latest_raw is None:
            raise ValueError(
                f"No source date found in response "
                f"for {dataset_name}"
            )

        actual_latest = parse_date(
            actual_latest_raw
        )

        # --------------------------------------------------
        # 6. Store original API response in Bronze
        # --------------------------------------------------

        s3_uri = writer.upload_raw_json(
            data=response,
            dataset=dataset_name,
        )

        logger.info(
            "%s | Uploaded %s records to %s",
            dataset_name,
            len(data),
            s3_uri,
        )

        # --------------------------------------------------
        # 7. Update state only after successful S3 upload
        # --------------------------------------------------

        state.update(
            dataset=dataset_name,
            last_source_date=actual_latest.isoformat(),
        )

        logger.info(
            "%s | State updated to %s",
            dataset_name,
            actual_latest,
        )

        updated += 1

    # ------------------------------------------------------
    # Airflow-friendly summary
    # ------------------------------------------------------

    logger.info(
        "INGESTION SUMMARY | checked=%s | updated=%s | skipped=%s",
        checked,
        updated,
        skipped,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    run_ingestion()