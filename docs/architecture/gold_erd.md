# Gold Data Model – ERD

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
