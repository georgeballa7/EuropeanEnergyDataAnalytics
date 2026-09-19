"""Gezielter historischer Backfill für neu in den Projektscope aufgenommene Länder.

Der Backfill ist bewusst vom normalen inkrementellen Ingestion-State getrennt.
Er lädt historische Ember-Daten für eine explizite Länderliste und schreibt die
vollständige API-Antwort in Bronze. Der reguläre State wird dabei weder gelesen
noch verändert.

Beispiel:
    python -m src.ingestion.run_backfill --countries AUT CHE NOR --datasets generation demand

Ohne ``--datasets`` werden alle konfigurierten Datensätze berücksichtigt. Bei
Datensätzen mit eingeschränkter Quellabdeckung (z. B. installed capacity) wird
die angeforderte Länderliste automatisch mit dem konfigurierten Dataset-Scope
geschnitten.
"""

import argparse
import logging
from collections.abc import Iterable

from config.settings import load_config
from src.ingestion.ember_client import EmberClient
from src.ingestion.s3_writer import S3Writer


logger = logging.getLogger(__name__)


def _unique(values: Iterable[str]) -> list[str]:
    """Entferne Duplikate, ohne die Reihenfolge zu verändern."""
    return list(dict.fromkeys(value.upper() for value in values))


def resolve_backfill_countries(
    requested_countries: list[str],
    project_countries: list[str],
    dataset_countries: list[str] | None = None,
) -> list[str]:
    """Bestimme die für einen Datensatz tatsächlich zulässigen Backfill-Länder."""
    project_scope = set(project_countries)
    requested = _unique(requested_countries)

    unknown = [country for country in requested if country not in project_scope]
    if unknown:
        raise ValueError(
            "Backfill enthält Länder außerhalb des Projektscopes: "
            + ", ".join(unknown)
        )

    allowed = set(dataset_countries or project_countries)
    return [country for country in requested if country in allowed]


def run_backfill(
    countries: list[str],
    dataset_names: list[str] | None = None,
    start_date: str | None = None,
) -> None:
    """Lade historische Daten für ausgewählte Länder nach Bronze.

    Der Backfill verändert den normalen Ingestion-State absichtlich nicht.
    Dadurch bleibt die Grenze für zukünftige inkrementelle Monatsläufe
    unverändert.
    """
    config = load_config()
    project_countries = config["countries"]
    datasets = config["datasets"]
    effective_start_date = start_date or config["source"]["start_date"]

    if dataset_names is None:
        selected_datasets = datasets
    else:
        invalid = [name for name in dataset_names if name not in datasets]
        if invalid:
            raise ValueError(
                "Unbekannte Datensätze: " + ", ".join(invalid)
            )
        selected_datasets = {name: datasets[name] for name in dataset_names}

    client = EmberClient()
    writer = S3Writer(
        bucket_name=config["project"]["bucket"],
        region_name=config["project"]["region"],
        profile_name=config["aws"].get("profile_name"),
        bronze_prefix=config["storage"]["bronze_prefix"],
    )

    written = 0
    skipped = 0

    logger.info(
        "Starte historischen Backfill | Länder=%s | Start=%s | Datensätze=%s",
        len(countries),
        effective_start_date,
        ",".join(selected_datasets),
    )

    for dataset_name, dataset_config in selected_datasets.items():
        effective_countries = resolve_backfill_countries(
            requested_countries=countries,
            project_countries=project_countries,
            dataset_countries=dataset_config.get("countries"),
        )

        if not effective_countries:
            logger.info(
                "Überspringe %s: Keines der angeforderten Länder ist für diesen Datensatz verfügbar.",
                dataset_name,
            )
            skipped += 1
            continue

        logger.info(
            "Backfill %s | Länder=%s | Start=%s",
            dataset_name,
            ",".join(effective_countries),
            effective_start_date,
        )

        response = client.fetch_dataset(
            endpoint=dataset_config["endpoint"],
            countries=effective_countries,
            start_date=effective_start_date,
        )
        data = response.get("data", [])

        if not data:
            logger.warning(
                "%s | API lieferte keine Daten. Kein Bronze-Objekt geschrieben.",
                dataset_name,
            )
            skipped += 1
            continue

        s3_uri = writer.upload_raw_json(
            data=response,
            dataset=dataset_name,
        )
        written += 1

        logger.info(
            "%s | %s Datensätze nach %s geschrieben.",
            dataset_name,
            len(data),
            s3_uri,
        )

    logger.info(
        "BACKFILL-ZUSAMMENFASSUNG | geschrieben=%s | übersprungen=%s | State unverändert",
        written,
        skipped,
    )


def parse_args() -> argparse.Namespace:
    """Lese CLI-Argumente für einen expliziten, kontrollierten Backfill."""
    parser = argparse.ArgumentParser(
        description="Historischer Ember-Backfill für ausgewählte Projektländer.",
    )
    parser.add_argument(
        "--countries",
        nargs="+",
        required=True,
        help="ISO/entity_codes der neu zu ladenden Länder, z. B. AUT CHE NOR.",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=None,
        help="Optional: generation demand emissions carbon_intensity capacity.",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Optionaler Startmonat/-tag. Standard ist source.start_date aus der YAML.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    args = parse_args()
    run_backfill(
        countries=args.countries,
        dataset_names=args.datasets,
        start_date=args.start_date,
    )
