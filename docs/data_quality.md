# Data Quality

Data-quality checks are executed before validated data is persisted in the Silver and Gold layers.

## Silver

Each dataset has an explicit business key and required measurement columns. Validation checks:

- required columns
- duplicate business keys
- null values in business-key and measurement columns
- unexpected countries outside the configured project scope

The validation deliberately does not require every dataset to contain all 20 countries because source coverage differs, particularly for installed capacity. Detailed Silver rules are available in [`silver_data_quality_guidelines.md`](decisions/silver_data_quality_guidelines.md).

## Gold

The dimensional model is validated for:

- unique and non-null dimension keys
- unique fact-table grain
- non-null required measures
- referential integrity between facts and dimensions

Gold is persisted only after the complete model passes validation.

## Source-Aware Validation

The project avoids generic cleaning rules that would alter valid source semantics. Statistical outliers are retained, missing observations are not imputed, negative net-import values are allowed, and aggregate-series metadata is preserved to support correct analytical aggregation.

A successful DQ result therefore means that the data satisfies the project's defined structural and relational rules; it does not imply identical temporal or geographic coverage across all source datasets.
