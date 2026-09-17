"""Orchestriere die monatliche European-Energy-Datenpipeline mit Airflow.

Der DAG führt die Verarbeitung sequenziell von der inkrementellen
Bronze-Ingestion über Silver und Gold bis zur Synchronisierung des AWS Glue
Data Catalog aus. Fehlgeschlagene DAG-Läufe lösen eine Slack-Benachrichtigung
aus.
"""

import pendulum

from airflow.sdk import DAG, task

from src.catalog.glue_catalog import update_glue_catalog
from src.ingestion.run_ingestion import run_ingestion
from src.transformation.run_gold_transformation import main as run_gold
from src.transformation.run_silver_transformation import main as run_silver
from src.utils.slack_notifications import notify_slack_failure


with DAG(
    dag_id="european_energy_pipeline",
    start_date=pendulum.datetime(
        2026,
        9,
        1,
        tz="Europe/Berlin",
    ),
    schedule="0 14 10 * *",
    catchup=False,
    on_failure_callback=notify_slack_failure,
    tags=["energy", "ember", "aws", "s3", "glue"],
):

    @task
    def extract_and_load_bronze():
        """Lade neue Ember-Quelldaten inkrementell in die Bronze-Schicht."""
        run_ingestion()

    @task
    def transform_bronze_to_silver():
        """Bereinige und validiere Bronze-Daten für den Silver-Snapshot."""
        run_silver()

    @task
    def transform_silver_to_gold():
        """Erzeuge und validiere das dimensionale Gold-Modell aus Silver."""
        run_gold()

    @task
    def synchronize_glue_catalog():
        """Synchronisiere die Silver- und Gold-Tabellen mit dem Glue Catalog."""
        update_glue_catalog()

    bronze = extract_and_load_bronze()
    silver = transform_bronze_to_silver()
    gold = transform_silver_to_gold()
    glue = synchronize_glue_catalog()

    bronze >> silver >> gold >> glue
