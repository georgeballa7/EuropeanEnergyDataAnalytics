from datetime import datetime

from airflow.sdk import DAG, task

from src.ingestion.run_ingestion import run_ingestion


with DAG(
    dag_id="european_energy_pipeline",
    start_date=datetime(2026, 9, 1),
    schedule=None,
    catchup=False,
    tags=["energy", "ember", "aws", "s3"],
):

    @task
    def extract_and_load_bronze():
        run_ingestion()

    extract_and_load_bronze()