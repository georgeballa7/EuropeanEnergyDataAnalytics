# Phase B — AWS integration validation record (2026-11-09)

> **Status:** controlled direct-stage validation **passed** in the existing project
> AWS account, region `eu-central-1`. The feature remains in PR #14 pending
> a separately approved merge. This is an execution record, not instructions
> to rerun the jobs. Local timestamps are Europe/Berlin; the Core Gold snapshot
> identifier contains the corresponding UTC timestamp.

## Scope and evidence

- **Revision:** `feature/phase-b-centralize-aws-config`, latest verified
  documentation-era commit after the Windows SQL path fix: `1bba3f5a`.
- **Automated testing:** `python -m pytest -q` returned **88 passed in
  6.99 s** before the final SQL path regression test was added.
  GitHub Actions then passed Python tests and Terraform formatting/validation
  at commit `1bba3f5a`; see [Actions run 42534237119](https://github.com/georgeballa7/EuropeanEnergyDataAnalytics/actions/runs/42534237119).
- **Execution method:** local Windows PowerShell, Python `energy` environment,
  real S3/Glue services; independent AWS read-back and Athena queries.
  **The Airflow scheduler/DAG was not executed end to end.**
- **AWS identity and region:** checked before writes; project S3 bucket
  reachable. The application data bucket has SSE-S3 encryption but
  **bucket versioning is not enabled**. The separate Terraform state
  bucket's versioning is a different setting.

## Backups and preservation

Before the first Silver write:

- Five Silver Parquet source objects copied into
  `backups/pre-phase-b/20261108T223846Z-b91ad8ee8b5b/silver/`.
  Every destination's size and ETag matched its source, and the source
  was checked again for unintended changes.
- All **18** Glue table definitions (5 Silver, 9 Core Gold, 4 Analytics
  Gold) saved as encrypted JSON under the sibling
  `backups/pre-phase-b/20261108T223846Z-b91ad8ee8b5b/glue/`.
  Each object's size and SSE-S3 encryption were verified.
- Nine previous Core Gold files under `gold/<table>/<table>.parquet`
  were deliberately left untouched. New Core Gold files use separate
  prefixes; Glue rollback is **best effort**, not atomic across tables.

## Silver — PASSED

1. Ran `process_dataset(get_s3_client(), "demand")`: success.
2. Ran `python -m src.transformation.run_silver_transformation`.
   Four remaining datasets completed; `demand` reported:
   *Keine neuen Bronze-Objekte; Silver unverändert*.
3. Independently inspected all five S3 Silver objects and their
   `control/silver/<dataset>.json` manifests.

| Silver dataset | Bronze JSON objects | Snapshot ETag / manifest ETag | Recorded Bronze metadata |
| --- | ---: | --- | --- |
| generation | 4 | Match | Match |
| demand | 4 | Match | Match |
| emissions | 4 | Match | Match |
| carbon_intensity | 4 | Match | Match |
| capacity | 3 | Match | Match |

All 5 manifests have version `1`, refer to the correct Silver object and
match each source Bronze key, ETag and size. The total is **19 Bronze JSON
objects**. The `demand` no-op is direct evidence for checkpoint-based skip
behavior; it is not evidence that every failure/rebuild path was exercised.

## Core Gold and Athena — PASSED

Ran `python -m src.transformation.run_gold_transformation`.
Local pre-publication Gold data quality passed. All **nine** nonempty
Parquet files exist under `gold_snapshots/<table>/<snapshot-id>/`.
All nine Glue locations point to the corresponding new prefix with a shared
`core_gold_snapshot_id`:

`20261108T230827717025Z-58f338d3`

Afterward, Glue schema synchronization completed locally.
Nine independent Athena post-load checks in the
`european-energy-analytics` workgroup all **SUCCEEDED**, with zero
required-field nulls, invalid foreign keys and duplicate key groups.

| Core Gold table | Athena rows | DQ |
| --- | ---: | --- |
| dim_date | 201 | Pass |
| dim_country | 41 | Pass |
| dim_energy_series | 17 | Pass |
| dim_capacity_series | 5 | Pass |
| fact_generation | 79,569 | Pass |
| fact_emissions | 79,569 | Pass |
| fact_demand | 5,347 | Pass |
| fact_carbon_intensity | 5,347 | Pass |
| fact_capacity | 5,668 | Pass |

The query pattern matches `src/quality/athena_quality.py`:
nonempty, non-null required keys/measures, key uniqueness, and fact-to-dimension
referential integrity. This proves structural integrity, not completeness
or independent semantic correctness of every energy figure.

## Analytics Gold — PASSED for existing unchanged results

The first Windows invocation of `publish_all_marts()` failed before any
mart query due to the hard-coded Airflow SQL path
`/opt/airflow/project/sql/analytics/`. Fixed in
`src/analytics/mart_config.py` by deriving the SQL directory from the
repository root; added the default-path regression test. CI passed.

After pulling the fix, the local publisher returned `skipped=True` for
all four marts because their fingerprints had not changed.
Independent Glue metadata checks confirmed all four original snapshot
locations and matching stored row counts. All four live Athena
`SELECT COUNT(*)` checks **SUCCEEDED**:

| Analytics Gold table | Athena rows | Publisher |
| --- | ---: | --- |
| analytics_generation_demand_summary | 38 | Unchanged, skipped |
| analytics_energy_mix_transition_summary | 38 | Unchanged, skipped |
| analytics_emissions_carbon_intensity | 38 | Unchanged, skipped |
| analytics_installed_solar_wind_capacity | 10 | Unchanged, skipped |

**Important distinction:** the reporting-table read and *unchanged-result
skip* paths passed live; the **changed-result UNLOAD, temporary staging-table
validation and final Analytics Glue republish paths were not exercised live**
in this run. They are covered by the existing automated tests, but live
publication of genuinely changed reporting data remains a separate
future validation scenario.

## Remaining operational checks

- [x] Silver backup and complete Glue metadata backup.
- [x] Silver incremental manifests and unchanged-result skip.
- [x] Core Gold staging and nine correct Glue snapshot locations.
- [x] Nine Athena Core Gold quality queries.
- [x] Four existing Analytics Gold tables queryable via Athena and
      correct unchanged-fingerprint skip.
- [x] Python and Terraform CI checks at the SQL-path-fix commit.
- [ ] Full Airflow DAG execution (including scheduled Bronze ingestion).
- [ ] Live **changed-result** Analytics Gold UNLOAD/publish/rollback scenario.
- [ ] End-to-end Slack failure notification test.
- [ ] Additional operational review before enabling unattended runs.

**Not performed:** Terraform Apply, main-branch merge, data deletion, or
changes to bucket versioning. Preserve prior S3 backups, legacy Gold data
and old Analytics snapshots until the necessary recovery windows are agreed.
