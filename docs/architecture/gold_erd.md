# Gold Data Model – Core ERD and Analytics Marts

The analytical Gold layer uses a **Fact Constellation / Galaxy Schema**. Multiple fact tables represent different analytical processes while sharing conformed dimensions where their semantics are compatible.

```mermaid
erDiagram
    DIM_DATE ||--o{ FACT_GENERATION : "date"
    DIM_DATE ||--o{ FACT_EMISSIONS : "date"
    DIM_DATE ||--o{ FACT_DEMAND : "date"
    DIM_DATE ||--o{ FACT_CARBON_INTENSITY : "date"
    DIM_DATE ||--o{ FACT_CAPACITY : "date"

    DIM_COUNTRY ||--o{ FACT_GENERATION : "entity_code"
    DIM_COUNTRY ||--o{ FACT_EMISSIONS : "entity_code"
    DIM_COUNTRY ||--o{ FACT_DEMAND : "entity_code"
    DIM_COUNTRY ||--o{ FACT_CARBON_INTENSITY : "entity_code"
    DIM_COUNTRY ||--o{ FACT_CAPACITY : "entity_code"

    DIM_ENERGY_SERIES ||--o{ FACT_GENERATION : "series_key"
    DIM_ENERGY_SERIES ||--o{ FACT_EMISSIONS : "series_key"

    DIM_CAPACITY_SERIES ||--o{ FACT_CAPACITY : "capacity_series_key"

    DIM_DATE {
        timestamp date PK
        bigint year
        bigint quarter
        bigint month_number
        string month_name
        string year_month
        boolean is_complete_year
    }

    DIM_COUNTRY {
        string entity_code PK
        string country_name
        boolean eu_member_flag
    }

    DIM_ENERGY_SERIES {
        bigint series_key PK
        string series_name
        string technology_group
        string energy_category
        boolean is_aggregate_series
    }

    DIM_CAPACITY_SERIES {
        bigint capacity_series_key PK
        string series_name
        boolean is_aggregate_series
    }

    FACT_GENERATION {
        timestamp date FK
        string entity_code FK
        bigint series_key FK
        double generation_twh
        double share_of_generation_pct
    }

    FACT_EMISSIONS {
        timestamp date FK
        string entity_code FK
        bigint series_key FK
        double emissions_mtco2
        double share_of_emissions_pct
    }

    FACT_DEMAND {
        timestamp date FK
        string entity_code FK
        double demand_twh
    }

    FACT_CARBON_INTENSITY {
        timestamp date FK
        string entity_code FK
        double emissions_intensity_gco2_per_kwh
    }

    FACT_CAPACITY {
        timestamp date FK
        string entity_code FK
        bigint capacity_series_key FK
        double capacity_gw
        double capacity_w_per_capita
    }
```

## Fact Table Grain

| Fact table | Grain |
|---|---|
| `fact_generation` | Country × month × energy series |
| `fact_emissions` | Country × month × energy series |
| `fact_demand` | Country × month |
| `fact_carbon_intensity` | Country × month |
| `fact_capacity` | Country × month × capacity series |

## Key Strategy

- `dim_date` uses the monthly date as a stable natural key.
- `dim_country` uses `entity_code` as a stable business key.
- `dim_energy_series` uses `series_key` for generation and emissions.
- `dim_capacity_series` uses a separate `capacity_series_key` because capacity-series aggregation semantics can differ from generation and emissions.

The PK/FK relationships shown here are logical analytical relationships. Athena does not physically enforce these constraints.

## Analytics Gold reporting layer

The **Core Gold ERD above remains the authoritative dimensional model**. The four reporting marts are derived country-and-comparison-period datasets, not additional fact tables at the monthly grain. They have no physically enforced foreign keys in Athena and should not be drawn as if they join directly to `dim_date` at month grain.

### Reporting marts and lineage

```mermaid
flowchart TB
    subgraph CORE["Core Gold · dimensional model"]
        C["dim_country · dim_date"]
        E["dim_energy_series · dim_capacity_series"]
        G["fact_generation"]
        D["fact_demand"]
        M["fact_emissions"]
        I["fact_carbon_intensity"]
        K["fact_capacity"]
    end

    G --> GD["analytics_generation_demand_summary"]
    D --> GD
    C --> GD
    G --> MIX["analytics_energy_mix_transition_summary"]
    E --> MIX
    C --> MIX
    M --> EM["analytics_emissions_carbon_intensity"]
    I --> EM
    E --> EM
    C --> EM
    K --> CAP["analytics_installed_solar_wind_capacity"]
    E --> CAP
    C --> CAP
```

All four marts derive year boundaries from Core Gold date coverage. The edges show **SQL derivation dependencies**, not database foreign-key constraints. The last two marts expose `country_name` but **not** `entity_code`, so they cannot be joined to `dim_country` on a code without a schema change or a separate mapping.

### Reporting-mart grain and logical keys

| Analytics Gold table | Grain | Logical uniqueness checked at publication |
| --- | --- | --- |
| `analytics_generation_demand_summary` | Country × start year × end year | `country_name, start_year, end_year` |
| `analytics_energy_mix_transition_summary` | Country × start year × end year | `country_name, start_year, end_year` |
| `analytics_emissions_carbon_intensity` | Country × start year × end year | `country_name, start_year, end_year` |
| `analytics_installed_solar_wind_capacity` | Country × start year × end year | `country_name, start_year, end_year` |

These are logical analytical grains. Athena/Glue do not enforce primary-key or foreign-key constraints. See the [data dictionary](../data_dictionary/data_dictionary.md) and [versioned SQL](../../sql/analytics/) for exact measures.

The Core Gold ERD contains **nine tables** (four dimensions, five facts); the lineage diagram above documents the separate Analytics Gold marts. The pipeline additionally publishes four country-level Analytics Gold tables through Athena UNLOAD, S3 Parquet and Glue: `analytics_generation_demand_summary`, `analytics_energy_mix_transition_summary`, `analytics_emissions_carbon_intensity` and `analytics_installed_solar_wind_capacity`. They compare 2019–2025 and are additive to Core Gold. Verified reporting rows (2026-10-14): **38 / 38 / 38 / 10**; Core Gold is configured for 41 European markets and installed capacity ingestion for 13.
