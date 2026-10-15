"""Publish validated reporting snapshots without modifying existing Gold tables.

Athena UNLOAD writes Parquet into an immutable S3 prefix. The Glue table
location is switched only after successful query execution and validation.
Previous snapshots are retained for rollback.
"""

import copy
import hashlib
import json
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


def glue_compatible_type(athena_type: str) -> str:
    """Translate Athena result types to Glue/Hive-compatible types."""
    normalized = athena_type.strip().lower()
    if normalized == "varchar" or normalized.startswith("varchar("):
        return "string"
    if normalized == "integer":
        return "int"
    return normalized


def get_columns(client, select_sql: str) -> list[dict]:
    query_id = execute(client, f"SELECT * FROM ({select_sql}) AS report LIMIT 0")
    metadata = client.get_query_results(QueryExecutionId=query_id, MaxResults=1)["ResultSet"]["ResultSetMetadata"]
    columns = [
        {"Name": col["Name"], "Type": glue_compatible_type(col["Type"])}
        for col in metadata["ColumnInfo"]
    ]
    if not columns:
        raise ValueError("Reporting query returned no columns")
    return columns


def source_fingerprint(client, sql: str) -> str:
    """Hash the actual reporting result and SQL, not the Airflow run ID.

    Sorting rows makes the fingerprint independent of Athena's row order.
    This is suitable for our small country-level reporting marts.
    """
    query_id = execute(client, sql)
    rows = []
    token = None
    first_page = True
    columns = None
    while True:
        kwargs = {"QueryExecutionId": query_id, "MaxResults": 1000}
        if token:
            kwargs["NextToken"] = token
        result = client.get_query_results(**kwargs)
        if columns is None:
            columns = [(c["Name"], c["Type"]) for c in result["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
        page = result["ResultSet"].get("Rows", [])
        if first_page:
            page = page[1:]  # Athena SELECT result header
            first_page = False
        for row in page:
            rows.append([value.get("VarCharValue") for value in row["Data"]])
        token = result.get("NextToken")
        if not token:
            break
    if not rows:
        raise ValueError("Reporting query returned no rows")
    payload = json.dumps(
        {"sql": sql, "columns": columns, "rows": sorted(rows, key=lambda row: json.dumps(row))},
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_mart(mart_name: str, athena=None, glue=None) -> dict:
    if mart_name not in REPORTING_MARTS:
        raise ValueError(f"Unknown analytics mart: {mart_name}")

    athena = athena or boto3.client("athena", region_name=REGION_NAME)
    glue = glue or boto3.client("glue", region_name=REGION_NAME)
    sql = load_mart_sql(mart_name)
    fingerprint = source_fingerprint(athena, sql)
    table_name = mart_table_name(mart_name)
    try:
        current_table = glue.get_table(DatabaseName=DATABASE_NAME, Name=table_name)["Table"]
    except glue.exceptions.EntityNotFoundException:
        current_table = None
    if current_table and current_table.get("Parameters", {}).get("analytics_fingerprint") == fingerprint:
        return {
            "mart": mart_name,
            "rows": int(current_table["Parameters"]["analytics_row_count"]),
            "location": current_table["StorageDescriptor"]["Location"],
            "skipped": True,
            "previous_table": current_table,
            "table_input": None,
        }
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
    staging_input = {
        "Name": staging_table,
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
    glue.create_table(DatabaseName=DATABASE_NAME, TableInput=staging_input)
    try:
        query_id = execute(
            athena,
            f'SELECT COUNT(*) AS total_rows FROM "{DATABASE_NAME}"."{staging_table}"',
        )
        rows = athena.get_query_results(QueryExecutionId=query_id)["ResultSet"]["Rows"]
        count = int(rows[1]["Data"][0]["VarCharValue"])
        if count <= 0:
            raise ValueError(f"Empty analytics snapshot: {mart_name}")

        # All four reporting marts are one-row-per-country comparisons.
        # Do not publish incomplete or duplicated country-level results.
        names = {col["Name"] for col in columns}
        if "country_name" not in names or not {"start_year", "end_year"} <= names:
            raise ValueError(f"Missing reporting dimensions: {mart_name}")
        check_id = execute(
            athena,
            f'SELECT COUNT(*) AS invalid_rows FROM "{DATABASE_NAME}"."{staging_table}" '
            'WHERE country_name IS NULL OR start_year IS NULL OR end_year IS NULL',
        )
        check_rows = athena.get_query_results(QueryExecutionId=check_id)["ResultSet"]["Rows"]
        invalid = int(check_rows[1]["Data"][0]["VarCharValue"])
        if invalid:
            raise ValueError(f"Invalid reporting dimensions in {mart_name}: {invalid}")
        duplicate_id = execute(
            athena,
            f'SELECT COUNT(*) AS duplicate_groups FROM (SELECT country_name, start_year, end_year '
            f'FROM "{DATABASE_NAME}"."{staging_table}" '
            'GROUP BY country_name, start_year, end_year HAVING COUNT(*) > 1)',
        )
        duplicate_rows = athena.get_query_results(QueryExecutionId=duplicate_id)["ResultSet"]["Rows"]
        duplicates = int(duplicate_rows[1]["Data"][0]["VarCharValue"])
        if duplicates:
            raise ValueError(f"Duplicate reporting country-period rows in {mart_name}: {duplicates}")
    finally:
        glue.delete_table(DatabaseName=DATABASE_NAME, Name=staging_table)

    table_input = {
        "Name": table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "parquet", "EXTERNAL": "TRUE",
                       "analytics_fingerprint": fingerprint, "analytics_row_count": str(count)},
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
    return {
        "mart": mart_name, "rows": count, "location": snapshot_uri,
        "skipped": False, "previous_table": current_table,
        "table_input": table_input,
    }


def _restore_table_input(table: dict) -> dict:
    """Keep only Glue CreateTable/UpdateTable-compatible definition fields."""
    allowed = {
        "Name", "Description", "Owner", "LastAccessTime", "LastAnalyzedTime",
        "Retention", "StorageDescriptor", "PartitionKeys", "ViewOriginalText",
        "ViewExpandedText", "TableType", "Parameters", "TargetTable",
        "ViewDefinition",
    }
    return {key: copy.deepcopy(value) for key, value in table.items() if key in allowed}


def _publish_prepared(prepared: dict, glue) -> None:
    if prepared["skipped"]:
        return
    name = mart_table_name(prepared["mart"])
    args = {"DatabaseName": DATABASE_NAME, "TableInput": prepared["table_input"]}
    if prepared["previous_table"] is None:
        glue.create_table(**args)
    else:
        glue.update_table(**args)


def _rollback_prepared(prepared: dict, glue) -> None:
    name = mart_table_name(prepared["mart"])
    previous = prepared["previous_table"]
    if previous is None:
        glue.delete_table(DatabaseName=DATABASE_NAME, Name=name)
    else:
        glue.update_table(
            DatabaseName=DATABASE_NAME,
            TableInput=_restore_table_input(previous),
        )


def publish_mart(mart_name: str, athena=None, glue=None) -> dict:
    """Publish one mart; preserve the existing single-mart public API."""
    glue = glue or boto3.client("glue", region_name=REGION_NAME)
    prepared = prepare_mart(mart_name, athena=athena, glue=glue)
    _publish_prepared(prepared, glue)
    return {key: prepared[key] for key in ("mart", "rows", "location", "skipped")}


def publish_all_marts(athena=None, glue=None) -> list[dict]:
    """Prepare every mart before changing any production Glue table.

    Glue updates are not atomic across tables. If a commit fails, attempt
    best-effort rollback of every touched table, including the failing one.
    Snapshots remain immutable for investigation and later cleanup.
    """
    athena = athena or boto3.client("athena", region_name=REGION_NAME)
    glue = glue or boto3.client("glue", region_name=REGION_NAME)
    prepared = [prepare_mart(name, athena=athena, glue=glue) for name in REPORTING_MARTS]
    touched = []
    try:
        for item in prepared:
            if item["skipped"]:
                continue
            touched.append(item)
            _publish_prepared(item, glue)
    except Exception as exc:
        rollback_errors = []
        for item in reversed(touched):
            try:
                _rollback_prepared(item, glue)
            except Exception as rollback_exc:
                rollback_errors.append(f'{item["mart"]}: {rollback_exc}')
        if rollback_errors:
            raise RuntimeError(
                f"Analytics publication failed ({exc}); rollback incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    return [{key: item[key] for key in ("mart", "rows", "location", "skipped")} for item in prepared]
