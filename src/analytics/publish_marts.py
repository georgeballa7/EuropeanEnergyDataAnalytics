"""Publish validated reporting snapshots without modifying existing Gold tables.

Athena UNLOAD writes Parquet into an immutable S3 prefix. The Glue table
location is switched only after successful query execution and validation.
Previous snapshots are retained for rollback.
"""

import time
import uuid

import boto3

from src.analytics.mart_config import DATABASE_NAME, REPORTING_MARTS, mart_s3_uri, mart_table_name
from src.analytics.sql_loader import load_mart_sql
from src.catalog.glue_catalog import REGION_NAME
from src.quality.athena_quality import WORKGROUP

POLL_INTERVAL_SECONDS = 2
MAX_POLLS = 300


def wait_for_query(client, query_id: str) -> None:
    for _ in range(MAX_POLLS):
        status = client.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            return
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Athena query {query_id} {state}: {status.get('StateChangeReason', '')}")
        time.sleep(POLL_INTERVAL_SECONDS)
    client.stop_query_execution(QueryExecutionId=query_id)
    raise TimeoutError(f"Athena query {query_id} timed out")


def execute(client, query: str) -> str:
    result = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": DATABASE_NAME},
        WorkGroup=WORKGROUP,
    )
    query_id = result["QueryExecutionId"]
    wait_for_query(client, query_id)
    return query_id


def get_columns(client, select_sql: str) -> list[dict]:
    query_id = execute(client, f"SELECT * FROM ({select_sql}) AS report LIMIT 0")
    metadata = client.get_query_results(QueryExecutionId=query_id, MaxResults=1)["ResultSet"]["ResultSetMetadata"]
    columns = [
        {"Name": col["Name"], "Type": col["Type"]}
        for col in metadata["ColumnInfo"]
    ]
    if not columns:
        raise ValueError("Reporting query returned no columns")
    return columns


def publish_mart(mart_name: str, athena=None, glue=None) -> dict:
    if mart_name not in REPORTING_MARTS:
        raise ValueError(f"Unknown analytics mart: {mart_name}")

    athena = athena or boto3.client("athena", region_name=REGION_NAME)
    glue = glue or boto3.client("glue", region_name=REGION_NAME)
    sql = load_mart_sql(mart_name)
    columns = get_columns(athena, sql)

    # A unique destination avoids Athena UNLOAD's nonempty-prefix restriction.
    snapshot_uri = f"{mart_s3_uri(mart_name)}snapshots/{uuid.uuid4().hex}/"
    unload = (
        f"UNLOAD ({sql}) TO '{snapshot_uri}' "
        "WITH (format = 'PARQUET', compression = 'SNAPPY')"
    )
    execute(athena, unload)

    # Validate actual Parquet files, not merely the source SELECT.
    # Reading from the S3 snapshot requires the temporary external table;
    # create it under a unique name and remove it before publishing.
    staging_table = f"_staging_{mart_table_name(mart_name)}_{uuid.uuid4().hex[:12]}"
    column_ddl = ", ".join(f'"{col["Name"]}" {col["Type"]}' for col in columns)
    execute(
        athena,
        f'CREATE EXTERNAL TABLE "{DATABASE_NAME}"."{staging_table}" '
        f"({column_ddl}) STORED AS PARQUET LOCATION '{snapshot_uri}'",
    )
    try:
        query_id = execute(
            athena,
            f'SELECT COUNT(*) AS total_rows FROM "{DATABASE_NAME}"."{staging_table}"',
        )
        rows = athena.get_query_results(QueryExecutionId=query_id)["ResultSet"]["Rows"]
        count = int(rows[1]["Data"][0]["VarCharValue"])
        if count <= 0:
            raise ValueError(f"Empty analytics snapshot: {mart_name}")
    finally:
        execute(athena, f'DROP TABLE IF EXISTS "{DATABASE_NAME}"."{staging_table}"')

    table_name = mart_table_name(mart_name)
    table_input = {
        "Name": table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "parquet", "EXTERNAL": "TRUE"},
        "StorageDescriptor": {
            "Columns": columns,
            "Location": snapshot_uri,
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {"serialization.format": "1"},
            },
        },
    }
    try:
        glue.get_table(DatabaseName=DATABASE_NAME, Name=table_name)
    except glue.exceptions.EntityNotFoundException:
        glue.create_table(DatabaseName=DATABASE_NAME, TableInput=table_input)
    else:
        glue.update_table(DatabaseName=DATABASE_NAME, TableInput=table_input)
    return {"mart": mart_name, "rows": count, "location": snapshot_uri}


def publish_all_marts() -> list[dict]:
    """Run after the persisted Core Gold quality gate has succeeded."""
    return [publish_mart(name) for name in REPORTING_MARTS]
