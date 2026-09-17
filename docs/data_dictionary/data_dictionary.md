# Gold Data Dictionary

The Gold layer contains four dimensions and five fact tables. Column names correspond to the schemas registered in the AWS Glue Data Catalog.

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

Capacity has narrower geographic coverage than the core datasets. Missing countries therefore represent source-coverage limitations rather than automatically constituting a data-quality failure.
