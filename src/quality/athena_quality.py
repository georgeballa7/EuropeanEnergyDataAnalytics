"""Validate persisted Gold tables through Athena after Glue synchronization."""

import logging
import os
import time

import boto3

from src.catalog.glue_catalog import DATABASE_NAME, GOLD_TABLE_SCHEMAS, REGION_NAME
from src.quality.gold_quality import DIMENSION_KEYS, FACT_GRAINS, FACT_MEASURES

WORKGROUP = "european-energy-analytics"
POLL_SECONDS = 2
MAX_POLLS = 90
logger = logging.getLogger(__name__)

FOREIGN_KEYS = {
    "date": ("dim_date", "date"),
    "entity_code": ("dim_country", "entity_code"),
    "series_key": ("dim_energy_series", "series_key"),
    "capacity_series_key": ("dim_capacity_series", "capacity_series_key"),
}


def build_validation_query(table):
    """Return a single-row query checking persisted keys, measures and FK links."""
    if table not in GOLD_TABLE_SCHEMAS:
        raise ValueError(f"Unknown Gold table: {table}")
    keys = DIMENSION_KEYS.get(table, FACT_GRAINS.get(table))
    measures = FACT_MEASURES.get(table, [])
    columns = keys + measures
    joins = []
    fk_checks = []
    if table in FACT_GRAINS:
        for index, key in enumerate(keys):
            if key not in FOREIGN_KEYS:
                continue
            dim, dim_key = FOREIGN_KEYS[key]
            alias = f"d{index}"
            joins.append(
                f"LEFT JOIN {DATABASE_NAME}.{dim} {alias} "
                f"ON f.{key} = {alias}.{dim_key}"
            )
            fk_checks.append(f"{alias}.{dim_key} IS NULL")

    # GROUP BY counts duplicate key groups without string casts or delimiters.
    grain = ", ".join(keys)
    null_expr = " OR ".join(f"f.{column} IS NULL" for column in columns)
    fk_expr = " OR ".join(f"({condition})" for condition in fk_checks)
    select_fk = (
        f"COUNT_IF({fk_expr}) AS invalid_foreign_keys"
        if fk_checks else "CAST(0 AS BIGINT) AS invalid_foreign_keys"
    )
    return f"""
SELECT
    COUNT(*) AS total_records,
    COUNT_IF({null_expr}) AS null_required_fields,
    {select_fk},
    (SELECT COUNT(*) FROM (
        SELECT {grain} FROM {DATABASE_NAME}.{table}
        GROUP BY {grain} HAVING COUNT(*) > 1
    )) AS duplicate_key_groups
FROM {DATABASE_NAME}.{table} f
{' '.join(joins)}
"""


def execute_validation(client, table):
    """Run Athena query and fail closed on timeout, errors or invalid results."""
    query = build_validation_query(table)
    execution = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": DATABASE_NAME},
        WorkGroup=WORKGROUP,
    )
    query_id = execution["QueryExecutionId"]
    for _ in range(MAX_POLLS):
        status = client.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Athena validation failed for {table}: {status.get('StateChangeReason', state)}")
        time.sleep(POLL_SECONDS)
    else:
        try:
            client.stop_query_execution(QueryExecutionId=query_id)
        finally:
            raise TimeoutError(f"Athena validation timed out for {table}: {query_id}")

    rows = client.get_query_results(QueryExecutionId=query_id)["ResultSet"]["Rows"]
    if len(rows) < 2 or len(rows[1]["Data"]) != 4:
        raise ValueError(f"Unexpected Athena validation result for {table}")
    values = [int(cell["VarCharValue"]) for cell in rows[1]["Data"]]
    result = dict(zip(
        ("total_records", "null_required_fields", "invalid_foreign_keys", "duplicate_key_groups"),
        values,
    ))
    if result["total_records"] == 0 or any(values[1:]):
        raise ValueError(f"Gold validation failed for {table}: {result}")
    logger.info("Athena Gold validation passed: %s %s", table, result)
    return result


def validate_athena_gold():
    """Validate all Gold tables using the configured AWS credential chain."""
    profile = os.getenv("AWS_PROFILE")
    session = boto3.Session(profile_name=profile or None, region_name=REGION_NAME)
    client = session.client("athena")
    return {table: execute_validation(client, table) for table in GOLD_TABLE_SCHEMAS}
