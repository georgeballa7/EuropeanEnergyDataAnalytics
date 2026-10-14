# Data Quality

Data-quality checks run both before persistence in the Silver and Gold layers and after Glue catalog synchronization against the persisted Gold tables through Amazon Athena.

## Silver

Each dataset has an explicit business key and required measurement columns. Validation checks:

- required columns
- duplicate business keys
- null values in business-key and measurement columns
- unexpected countries outside the configured project scope

The validation deliberately does not require every dataset to contain every configured European market because source coverage differs by dataset. Generation, demand, emissions and carbon intensity use the 41-market European project scope, while installed capacity uses its configured Ember-supported subset. Detailed Silver rules are available in [`silver_data_quality_guidelines.md`](decisions/silver_data_quality_guidelines.md).

## Gold

The dimensional model is validated for:

- unique and non-null dimension keys
- unique fact-table grain
- non-null required measures
- referential integrity between facts and dimensions

Gold is persisted only after the complete model passes validation.

## Athena Post-Load Validation

The final Airflow task, `validate_persisted_gold`, queries all nine Gold tables using the existing `european-energy-analytics` Athena workgroup. It verifies:

- each dimension and fact table contains records
- required key and measure fields are non-null
- dimension keys and fact business keys are unique
- fact foreign keys resolve to the corresponding dimensions

The task fails on invalid data, Athena query errors or query timeouts. This checks the queryable data in S3 through the Glue catalog, complementing the in-memory transformation checks. See [`src/quality/athena_quality.py`](../src/quality/athena_quality.py) for the implementation. The checks validate structural integrity; they do not establish completeness of source coverage or independent correctness of all analytical measures.

## Source-Aware Validation

The project avoids generic cleaning rules that would alter valid source semantics. Statistical outliers are retained, missing observations are not imputed, negative net-import values are allowed, and aggregate-series metadata is preserved to support correct analytical aggregation.

A successful DQ result therefore means that the data satisfies the project's defined structural and relational rules; it does not imply identical temporal or geographic coverage across all source datasets.
