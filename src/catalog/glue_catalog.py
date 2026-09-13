"""
Manage AWS Glue Data Catalog tables for the Silver energy datasets.
"""

import boto3


DATABASE_NAME = "european_energy_analytics"

BUCKET_NAME = (
    "european-energy-data-analytics-488658242500-eu-central-1-an"
)

REGION_NAME = "eu-central-1"


TABLE_SCHEMAS = {
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


def get_glue_client(
    aws_profile: str | None = None,
):
    """Create an AWS Glue client."""

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
    dataset_name: str,
) -> dict:
    """Build the Glue table definition."""

    columns = [
        {
            "Name": name,
            "Type": data_type,
        }
        for name, data_type
        in TABLE_SCHEMAS[dataset_name]
    ]

    location = (
        f"s3://{BUCKET_NAME}/"
        f"silver/ember/{dataset_name}/"
    )

    return {
        "Name": dataset_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "parquet",
        },
        "StorageDescriptor": {
            "Columns": columns,
            "Location": location,
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
    dataset_name: str,
) -> None:
    """Create a Glue table or update it if it already exists."""

    table_input = build_table_input(
        dataset_name
    )

    try:
        glue_client.get_table(
            DatabaseName=DATABASE_NAME,
            Name=dataset_name,
        )

        glue_client.update_table(
            DatabaseName=DATABASE_NAME,
            TableInput=table_input,
        )

        print(f"Updated Glue table: {dataset_name}")

    except glue_client.exceptions.EntityNotFoundException:

        glue_client.create_table(
            DatabaseName=DATABASE_NAME,
            TableInput=table_input,
        )

        print(f"Created Glue table: {dataset_name}")


def update_glue_catalog(
    aws_profile: str | None = None,
) -> None:
    """Create or update all Silver Glue tables."""

    glue_client = get_glue_client(
        aws_profile=aws_profile
    )

    for dataset_name in TABLE_SCHEMAS:
        create_or_update_table(
            glue_client,
            dataset_name,
        )


if __name__ == "__main__":
    update_glue_catalog(
        aws_profile="energy-pipeline"
    )