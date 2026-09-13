"""
Verwalte die Tabellen des AWS Glue Data Catalog für die Silver- und Gold-Schicht.

Zweck
-----
Dieses Modul registriert die bekannten Parquet-Schemata des Projekts explizit
im AWS Glue Data Catalog. Dadurch können Amazon Athena und nachgelagerte
Analysewerkzeuge wie Power BI die Daten in Amazon S3 als Tabellen abfragen.

Architektur
-----------
Silver:
    Bereinigte, typisierte und validierte Ember-Daten unter
    ``s3://<bucket>/silver/ember/<dataset>/``.

Gold:
    Fachlich modellierte Dimensions- und Faktentabellen unter
    ``s3://<bucket>/gold/<table>/``.

Warum keine Crawler für Gold?
-----------------------------
Die Gold-Schemata werden vollständig durch unseren eigenen Transformationscode
kontrolliert und sind daher bekannt. Eine explizite Registrierung ist in diesem
Fall reproduzierbarer und vorhersehbarer als eine erneute Schema-Erkennung durch
Crawler.

Die Funktionen sind idempotent ausgelegt: Existiert eine Tabelle bereits, wird
sie aktualisiert; andernfalls wird sie erstellt.
"""

from __future__ import annotations

import boto3


DATABASE_NAME = "european_energy_analytics"

BUCKET_NAME = (
    "european-energy-data-analytics-488658242500-eu-central-1-an"
)

REGION_NAME = "eu-central-1"


# ---------------------------------------------------------------------
# Silver-Schemata
# ---------------------------------------------------------------------

SILVER_TABLE_SCHEMAS = {
    "generation": [
        ("entity", "string"),
        ("entity_code", "string"),
        ("is_aggregate_entity", "boolean"),
        ("date", "timestamp"),
        ("series", "string"),
        ("is_aggregate_series", "boolean"),
        ("generation_twh", "double"),
        ("share_of_generation_pct", "double"),
    ],
    "demand": [
        ("entity", "string"),
        ("entity_code", "string"),
        ("date", "timestamp"),
        ("demand_twh", "double"),
    ],
    "emissions": [
        ("entity", "string"),
        ("entity_code", "string"),
        ("is_aggregate_entity", "boolean"),
        ("date", "timestamp"),
        ("series", "string"),
        ("is_aggregate_series", "boolean"),
        ("emissions_mtco2", "double"),
        ("share_of_emissions_pct", "double"),
    ],
    "carbon_intensity": [
        ("entity", "string"),
        ("entity_code", "string"),
        ("date", "timestamp"),
        ("emissions_intensity_gco2_per_kwh", "double"),
    ],
    "capacity": [
        ("entity", "string"),
        ("entity_code", "string"),
        ("is_aggregate_entity", "boolean"),
        ("date", "timestamp"),
        ("series", "string"),
        ("is_aggregate_series", "boolean"),
        ("capacity_gw", "double"),
        ("capacity_w_per_capita", "double"),
    ],
}


# ---------------------------------------------------------------------
# Gold-Schemata
# ---------------------------------------------------------------------

GOLD_TABLE_SCHEMAS = {
    "dim_date": [
        ("date", "timestamp"),
        ("year", "bigint"),
        ("quarter", "bigint"),
        ("month_number", "bigint"),
        ("month_name", "string"),
        ("year_month", "string"),
        ("is_complete_year", "boolean"),
    ],
    "dim_country": [
        ("entity_code", "string"),
        ("country_name", "string"),
        ("eu_member_flag", "boolean"),
    ],
    "dim_energy_series": [
        ("series_key", "bigint"),
        ("series_name", "string"),
        ("technology_group", "string"),
        ("energy_category", "string"),
        ("is_aggregate_series", "boolean"),
    ],
    "dim_capacity_series": [
        ("capacity_series_key", "bigint"),
        ("series_name", "string"),
        ("is_aggregate_series", "boolean"),
    ],
    "fact_generation": [
        ("date", "timestamp"),
        ("entity_code", "string"),
        ("series_key", "bigint"),
        ("generation_twh", "double"),
        ("share_of_generation_pct", "double"),
    ],
    "fact_emissions": [
        ("date", "timestamp"),
        ("entity_code", "string"),
        ("series_key", "bigint"),
        ("emissions_mtco2", "double"),
        ("share_of_emissions_pct", "double"),
    ],
    "fact_demand": [
        ("date", "timestamp"),
        ("entity_code", "string"),
        ("demand_twh", "double"),
    ],
    "fact_carbon_intensity": [
        ("date", "timestamp"),
        ("entity_code", "string"),
        ("emissions_intensity_gco2_per_kwh", "double"),
    ],
    "fact_capacity": [
        ("date", "timestamp"),
        ("entity_code", "string"),
        ("capacity_series_key", "bigint"),
        ("capacity_gw", "double"),
        ("capacity_w_per_capita", "double"),
    ],
}


def get_glue_client(
    aws_profile: str | None = None,
):
    """
    Erstelle einen AWS-Glue-Client.

    Parameter
    ---------
    aws_profile:
        Optionaler Name eines lokal konfigurierten AWS-CLI-Profils.
        Wird kein Profil angegeben, verwendet boto3 die Standard-
        Credential-Provider-Chain, beispielsweise eine IAM-Rolle in AWS.

    Rückgabe
    --------
    botocore.client.BaseClient
        Konfigurierter Glue-Client für die Projektregion.
    """
    if aws_profile:
        session = boto3.Session(
            profile_name=aws_profile,
            region_name=REGION_NAME,
        )
    else:
        session = boto3.Session(
            region_name=REGION_NAME,
        )

    return session.client("glue")


def build_table_input(
    table_name: str,
    columns: list[tuple[str, str]],
    s3_location: str,
) -> dict:
    """
    Erzeuge die Glue-Tabellendefinition für eine Parquet-Tabelle.

    Parameter
    ---------
    table_name:
        Name der Tabelle im Glue Data Catalog.
    columns:
        Liste aus Spaltennamen und zugehörigen Glue-Datentypen.
    s3_location:
        S3-Präfix, unter dem die Parquet-Daten der Tabelle liegen.

    Rückgabe
    --------
    dict
        ``TableInput``-Struktur für ``create_table`` oder ``update_table``.

    Hinweise
    --------
    Die Daten bleiben physisch in Amazon S3. Glue speichert lediglich die
    Metadaten wie Tabellenname, Schema, Dateiformat und Speicherort.
    """
    glue_columns = [
        {
            "Name": name,
            "Type": data_type,
        }
        for name, data_type in columns
    ]

    return {
        "Name": table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "parquet",
        },
        "StorageDescriptor": {
            "Columns": glue_columns,
            "Location": s3_location,
            "InputFormat": (
                "org.apache.hadoop.hive.ql.io.parquet."
                "MapredParquetInputFormat"
            ),
            "OutputFormat": (
                "org.apache.hadoop.hive.ql.io.parquet."
                "MapredParquetOutputFormat"
            ),
            "SerdeInfo": {
                "SerializationLibrary": (
                    "org.apache.hadoop.hive.ql.io.parquet.serde."
                    "ParquetHiveSerDe"
                )
            },
        },
    }


def create_or_update_table(
    glue_client,
    table_name: str,
    columns: list[tuple[str, str]],
    s3_location: str,
) -> None:
    """
    Erstelle eine Glue-Tabelle oder aktualisiere eine vorhandene Tabelle.

    Die Funktion ist idempotent: Wiederholte Ausführungen erzeugen keine
    zusätzlichen Tabellen. Existiert die Tabelle bereits, werden Definition
    und S3-Speicherort auf den aktuellen Projektstand gebracht.
    """
    table_input = build_table_input(
        table_name=table_name,
        columns=columns,
        s3_location=s3_location,
    )

    try:
        glue_client.get_table(
            DatabaseName=DATABASE_NAME,
            Name=table_name,
        )

        glue_client.update_table(
            DatabaseName=DATABASE_NAME,
            TableInput=table_input,
        )

        print(f"Updated Glue table: {table_name}")

    except glue_client.exceptions.EntityNotFoundException:
        glue_client.create_table(
            DatabaseName=DATABASE_NAME,
            TableInput=table_input,
        )

        print(f"Created Glue table: {table_name}")


def update_silver_tables(
    glue_client,
) -> None:
    """Erstelle oder aktualisiere alle fünf Silver-Tabellen im Glue Catalog."""
    for table_name, columns in SILVER_TABLE_SCHEMAS.items():
        s3_location = (
            f"s3://{BUCKET_NAME}/"
            f"silver/ember/{table_name}/"
        )

        create_or_update_table(
            glue_client=glue_client,
            table_name=table_name,
            columns=columns,
            s3_location=s3_location,
        )


def update_gold_tables(
    glue_client,
) -> None:
    """Erstelle oder aktualisiere alle neun Gold-Tabellen im Glue Catalog."""
    for table_name, columns in GOLD_TABLE_SCHEMAS.items():
        s3_location = (
            f"s3://{BUCKET_NAME}/"
            f"gold/{table_name}/"
        )

        create_or_update_table(
            glue_client=glue_client,
            table_name=table_name,
            columns=columns,
            s3_location=s3_location,
        )


def update_glue_catalog(
    aws_profile: str | None = None,
) -> None:
    """
    Synchronisiere Silver- und Gold-Tabellen mit dem AWS Glue Data Catalog.

    Ein Lauf verwaltet insgesamt 14 externe Tabellen:
    fünf Tabellen der Silver-Schicht und neun Tabellen der Gold-Schicht.
    """
    glue_client = get_glue_client(
        aws_profile=aws_profile
    )

    update_silver_tables(glue_client)
    update_gold_tables(glue_client)


if __name__ == "__main__":
    update_glue_catalog(
        aws_profile="energy-pipeline"
    )
