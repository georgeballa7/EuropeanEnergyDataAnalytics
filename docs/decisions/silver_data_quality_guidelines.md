# Silver Data Quality Rules

## Dataset scope and historical period

The current configuration in `config/series_config.yaml` is the source of truth for dataset selection, requested start month and geographic scope.

| Dataset | Configured geographic scope | Business key |
| --- | --- | --- |
| `generation` | 41 European markets | `entity_code, date, series` |
| `demand` | 41 European markets | `entity_code, date` |
| `emissions` | 41 European markets | `entity_code, date, series` |
| `carbon_intensity` | 41 European markets | `entity_code, date` |
| `capacity` | 13 configured Ember-supported markets | `entity_code, date, series` |

The configured historical request start is **2010-01**, not a guarantee that every country, series or dataset has observations from that month. Source coverage and latest available month differ by dataset. A country absent from a dataset with narrower Ember coverage is not automatically a data-quality failure.

The Analytics Gold reporting marts are separate from Silver: the 2019–2025 country comparisons verified on 2026-10-14 contain 38 / 38 / 38 / 10 rows, respectively. Those counts are not the expected Silver country counts.

## Key uniqueness

Each dataset's business key in the table above must be unique in its validated Silver snapshot. Check duplicates on the complete snapshot, not only an individual Bronze ingestion object.

## Required fields

- `entity`, `entity_code`, `date` and the dataset's required measurement columns must be present and non-null according to the implemented validator.
- `series` and `is_aggregate_series` are required where the dataset schema contains energy or capacity series.
- Source availability, optional fields and legitimate source semantics must be distinguished from malformed records.

## Data types and source semantics

Dates are converted to date/datetime types, numeric measurements to numeric types, and aggregate flags to booleans.

Aggregate series are retained but must not be summed with their component series during analytical aggregation. Negative net imports are meaningful and must not be discarded solely because they are negative. Missing observations are not automatically imputed and statistical outliers are not automatically removed.

## Installed capacity

Installed capacity is one of the five ingested and modelled datasets, with its own `fact_capacity` and `dim_capacity_series` in Core Gold. Its **13-country configured ingestion scope** differs from the **10-country Analytics Gold solar/wind comparison**, which requires comparable observations for the reporting years. Earlier Bronze exploratory results covering 12 countries during 2016–2026 were historical snapshots, not current project-wide requirements.

## Validation and evidence

Silver validation precedes persistence of the merged Parquet snapshot. Gold model validation and the downstream Athena post-load gate independently check the nine Core Gold tables. See [data quality](../data_quality.md), [data dictionary](../data_dictionary/data_dictionary.md) and the [runbook](../operations/runbook.md) for the full workflow.
