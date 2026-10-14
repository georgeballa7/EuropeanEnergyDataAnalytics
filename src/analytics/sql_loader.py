"""Read and validate the version-controlled SQL used by Gold reporting marts."""

from pathlib import Path

from src.analytics.mart_config import ANALYTICS_SQL_DIRECTORY, REPORTING_MARTS


def load_mart_sql(mart_name: str, sql_directory: Path | None = None) -> str:
    """Load a registered single-statement SELECT query; never accept arbitrary paths."""
    try:
        filename = REPORTING_MARTS[mart_name]
    except KeyError as exc:
        raise ValueError(f"Unknown analytics mart: {mart_name}") from exc

    directory = Path(sql_directory) if sql_directory is not None else ANALYTICS_SQL_DIRECTORY
    sql = (directory / filename).read_text(encoding="utf-8").strip()
    # Existing queries end with a semicolon; strip it for embedding in CTAS/UNLOAD.
    sql = sql.rstrip(";").strip()
    # Comments are permitted, but only read-only SELECT/CTE statements are registered.
    import re
    statement = re.sub(r"(?m)^\s*--[^\n]*(?:\n|$)", "", sql).strip()
    if not re.match(r"(?is)^WITH\b|^SELECT\b", statement):
        raise ValueError(f"Reporting query must start with SELECT or WITH: {filename}")
    if ";" in statement:
        raise ValueError(f"Multiple SQL statements are not supported: {filename}")
    return sql
