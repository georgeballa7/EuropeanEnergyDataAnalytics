# Gold Data Dictionary

The Core Gold layer contains four dimensions and five fact tables. Four additional Analytics Gold reporting tables are published separately; they do not alter the Core Gold model or existing Power BI relationships. Column names correspond to the schemas registered in the AWS Glue Data Catalog.

## Dimensions

| Table | Grain / Purpose | Key | Main attributes |
|---|---|---|---|
| `dim_date` | One row per month | `date` | `year`, `quarter`, `month_number`, `month_name`, `year_month`, `is_complete_year` |
| `dim_country` | One row per country | `entity_code` | `country_name`, `eu_member_flag` |
| `dim_energy_series` | One row per generation/emissions energy series | `series_key` | `series_name`, `technology_group`, `energy_category`, `is_aggregate_series` |
| `dim_capacity_series` | One row per installed-capacity series | `capacity_series_key` | `series_name`, `is_aggregate_series` |

## Facts

| Table | Grain | Foreign keys | Measures |
|---|---|---|---|
| `fact_generation` | Country × month × energy series | `date`, `entity_code`, `series_key` | `generation_twh`, `share_of_generation_pct` |
| `fact_emissions` | Country × month × energy series | `date`, `entity_code`, `series_key` | `emissions_mtco2`, `share_of_emissions_pct` |
| `fact_demand` | Country × month | `date`, `entity_code` | `demand_twh` |
| `fact_carbon_intensity` | Country × month | `date`, `entity_code` | `emissions_intensity_gco2_per_kwh` |
| `fact_capacity` | Country × month × capacity series | `date`, `entity_code`, `capacity_series_key` | `capacity_gw`, `capacity_w_per_capita` |

## Measure Semantics

Generation and emissions contain aggregate as well as component series. These must not be summed together, because doing so would double count the underlying electricity generation or emissions.

`demand_twh` represents monthly electricity demand. Carbon intensity is an intensity measure and must not be summed across months. Installed capacity is a stock measure; monthly capacity observations must likewise not be summed when comparing installed capacity over time.

The four core monthly datasets have a configured 41-market scope; capacity ingestion has 13 configured markets. Capacity has narrower geographic coverage than the core datasets. Missing countries therefore represent source-coverage limitations rather than automatically constituting a data-quality failure.

## Analytics Gold Reporting Tables

Each reporting table contains country-level comparisons between a start and end year; a row is one country and comparison period. The actual reporting coverage is narrower than the configured 41-country source scope where comparison years or capacity data are unavailable.

| Glue table | Main fields | Verified rows (2026-10-14) |
| --- | --- | ---: |
| `analytics_generation_demand_summary` | `country_name`, `entity_code`, `start_year`, `end_year`, generation/demand TWh and change percentages, net imports TWh | 38 |
| `analytics_energy_mix_transition_summary` | `country_name`, `entity_code`, `start_year`, `end_year`, renewable/fossil/clean shares and percentage-point changes | 38 |
| `analytics_emissions_carbon_intensity` | `country_name`, `start_year`, `end_year`, emissions in MtCO2 and carbon-intensity changes | 38 |
| `analytics_installed_solar_wind_capacity` | `country_name`, `start_year`, `end_year`, solar/wind capacity in GW and percentage changes | 10 |

The latter two marts do not expose `entity_code`; do not assume identical schemas across reporting tables. A percentage-point change in a share is not the same as a percentage relative change. Source SQL definitions are maintained under [`sql/analytics/`](../../sql/analytics/).

## Bronze profile provenance

[`bronze_data_profile.csv`](bronze_data_profile.csv) is a **historical initial exploratory sample**, not an up-to-date inventory. Its recorded 20-country core coverage and 12-country capacity coverage describe that earlier source snapshot. The `profile_scope` column labels each row accordingly. Do not substitute those historical row counts for current Silver/Core Gold or Analytics Gold coverage. The notebook `notebooks/02_data_understanding.ipynb` can regenerate a new profile after deliberately selecting and loading an appropriate source snapshot.
