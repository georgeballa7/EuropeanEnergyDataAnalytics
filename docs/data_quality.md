# Data Quality

Data-quality checks run both before persistence in the Silver and Gold layers and after Glue catalog synchronization against the persisted Gold tables through Amazon Athena.

## Silver

Each dataset has an explicit business key and required measurement columns. Validation checks:

- required columns
- duplicate business keys
- null values in business-key and measurement columns
- unexpected countries outside the configured project scope

The validation deliberately does not require every dataset to contain every configured European market because source coverage differs by dataset. Generation, demand, emissions and carbon intensity use the 41-market European project scope, while installed capacity uses **13 configured Ember-supported markets**. The API request start is **2010-01**; actual historical availability can be shorter and differs by dataset and market. Detailed Silver rules are available in [`silver_data_quality_guidelines.md`](decisions/silver_data_quality_guidelines.md).

## Gold

The dimensional model is validated for:

- unique and non-null dimension keys
- unique fact-table grain
- non-null required measures
- referential integrity between facts and dimensions

Gold is persisted only after the complete model passes validation.

## Athena Post-Load Validation

The fifth Airflow task, `validate_persisted_gold`, queries all nine Gold tables using the existing `european-energy-analytics` Athena workgroup. It verifies:

- each dimension and fact table contains records
- required key and measure fields are non-null
- dimension keys and fact business keys are unique
- fact foreign keys resolve to the corresponding dimensions

The task fails on invalid data, Athena query errors or query timeouts. This checks the queryable data in S3 through the Glue catalog, complementing the in-memory transformation checks. See [`src/quality/athena_quality.py`](../src/quality/athena_quality.py) for the implementation. The checks validate structural integrity; they do not establish completeness of source coverage or independent correctness of all analytical measures.

## Analytics Gold Publication Checks

After the Core Gold Athena quality gate, the sixth task `publish_analytics_gold` publishes four additional reporting marts. For each mart it checks that the Parquet snapshot can be queried through a temporary Glue table, contains at least one row, has non-null `country_name`, `start_year` and `end_year`, and has no duplicate country-period combinations. The final Glue table is updated only after those checks succeed. Temporary Glue tables are removed after validation.

The published mart counts verified in Athena on 2026-10-14 were 38 (generation/demand), 38 (energy mix), 38 (emissions/intensity), and 10 (solar/wind capacity). These counts do not imply that the 41-market configured scope was reduced. Missing period comparisons and narrower capacity source coverage affect reporting completeness.

For unchanged SQL and result data, a stored fingerprint prevents repeat publication; this does not provide atomic publication across all four marts or guarantee that failed UNLOAD snapshots are automatically removed.

## Source-Aware Validation

The project avoids generic cleaning rules that would alter valid source semantics. Statistical outliers are retained, missing observations are not imputed, negative net-import values are allowed, and aggregate-series metadata is preserved to support correct analytical aggregation.

A successful DQ result therefore means that the data satisfies the project's defined structural and relational rules; it does not imply identical temporal or geographic coverage across all source datasets.

## Historical Bronze profile

The checked-in [`bronze_data_profile.csv`](data_dictionary/bronze_data_profile.csv) is an initial exploratory sample (20 core countries and 12 capacity countries), not a live data-quality baseline. Its `profile_scope` field explicitly marks historical observations. Validate current country coverage and periods from the configured scope and actual persisted Silver/Gold data, rather than assuming the old CSV counts remain current.
