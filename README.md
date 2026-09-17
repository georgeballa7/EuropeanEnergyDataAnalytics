# European Energy Data Analytics

End-to-end ELT and analytics project for monthly European electricity data from the Ember Energy API.

## Architecture

`Ember API → Airflow → Amazon S3 Bronze → Silver → Gold → AWS Glue → Amazon Athena → Power BI`

## Tech Stack

Python · pandas · Apache Airflow · Docker · Amazon S3 · AWS Glue · Amazon Athena · Parquet · SQL · Power BI

## Highlights

- Incremental monthly API ingestion with persistent S3 state
- Bronze / Silver / Gold medallion architecture
- Automated Silver and Gold data-quality checks
- Dimensional Gold model with conformed dimensions
- Monthly Airflow orchestration and Slack failure notifications
- Serverless SQL analytics with Athena
- Power BI reporting across 20 European countries

## Power BI Dashboard

![Executive Overview](powerbi/screenshots/Page02.png)

[View the complete Power BI report (PDF)](powerbi/EuropeanEnergyAnalytics.pdf)

## Analytics

The project analyses electricity generation and demand, energy-mix transition, power-sector emissions and carbon intensity, and installed solar and wind capacity. The final Athena SQL queries are available in [`sql/analytics/`](sql/analytics/).

## Documentation

- [Architecture](docs/architecture/architecture.md)
- [Gold Data Model / ERD](docs/architecture/gold_erd.md)
- [Data Dictionary](docs/data_dictionary/data_dictionary.md)
- [Data Quality](docs/data_quality.md)
- [Architecture Decisions](docs/decisions/architecture_decisions.md)

Exploration, data understanding and EDA are documented in [`notebooks/`](notebooks/).
