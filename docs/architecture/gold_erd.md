# Gold-Datenmodell – ERD

Dieses Diagramm dokumentiert das analytische Gold-Modell des Projekts als **Fact Constellation / Galaxy Schema**.

Mehrere Faktentabellen bilden unterschiedliche fachliche Prozesse ab und teilen sich gemeinsame Dimensionen. Die Beziehungen sind im Gold-Modell logisch definiert und werden später auch im semantischen Modell von Power BI verwendet.

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

## Grain der Faktentabellen

| Faktentabelle | Grain |
|---|---|
| `fact_generation` | Land × Monat × Energiereihe |
| `fact_emissions` | Land × Monat × Energiereihe |
| `fact_demand` | Land × Monat |
| `fact_carbon_intensity` | Land × Monat |
| `fact_capacity` | Land × Monat × Kapazitätsreihe |

## Schlüsselstrategie

- `dim_date` verwendet das Monatsdatum als stabilen natürlichen Schlüssel.
- `dim_country` verwendet `entity_code` als stabilen Business Key.
- `dim_energy_series` verwendet `series_key` als Surrogate Key für Generation und Emissionen.
- `dim_capacity_series` verwendet einen separaten `capacity_series_key`, weil die Semantik einzelner Reihen – insbesondere `Wind` – zwischen Capacity und den übrigen Datensätzen unterschiedlich sein kann.

## Architekturhinweis

Die physischen Gold-Daten liegen als Parquet-Dateien in Amazon S3. Der AWS Glue Data Catalog verwaltet die Tabellenschemata und Amazon Athena verwendet diese Metadaten für serverlose SQL-Abfragen direkt auf S3. Die hier dargestellten PK-/FK-Beziehungen sind logische Modellbeziehungen und keine physisch erzwungenen Constraints in Athena.
