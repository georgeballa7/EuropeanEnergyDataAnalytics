"""Configuration for additive, Power BI-safe Gold analytics marts.

Core Gold fact and dimension tables remain unchanged. Reporting marts use
separate S3 prefixes and Glue table names.
"""

from pathlib import Path

from src.catalog.glue_catalog import BUCKET_NAME, DATABASE_NAME

ANALYTICS_SQL_DIRECTORY = Path("/opt/airflow/project/sql/analytics")
ANALYTICS_GOLD_PREFIX = "gold/analytics"

# Each reporting mart is built from an existing, version-controlled SQL query.
REPORTING_MARTS = {
    "generation_demand_summary": "01_generation_demand_summary.sql",
    "energy_mix_transition_summary": "02_energy_mix_transition_summary.sql",
    "emissions_carbon_intensity": "03_emissions_carbon_intensity.sql",
    "installed_solar_wind_capacity": "04_installed_solar_wind_capacity.sql",
}


def mart_s3_uri(mart_name: str) -> str:
    """Return the dedicated Gold location for a registered reporting mart."""
    if mart_name not in REPORTING_MARTS:
        raise ValueError(f"Unknown analytics mart: {mart_name}")
    return f"s3://{BUCKET_NAME}/{ANALYTICS_GOLD_PREFIX}/{mart_name}/"


def mart_table_name(mart_name: str) -> str:
    """Keep reporting tables separate from existing Gold model tables."""
    if mart_name not in REPORTING_MARTS:
        raise ValueError(f"Unknown analytics mart: {mart_name}")
    return f"analytics_{mart_name}"
