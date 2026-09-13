# Silver Data Quality Rules

## Core datasets

Core datasets:

- generation
- demand
- emissions
- carbon_intensity

Expected country coverage:

- 20 configured European countries

Analysis period:

- 2010-01-01 to latest available month

## Key uniqueness

| Dataset | Business Key |
|---|---|
| generation | entity_code, date, series |
| demand | entity_code, date |
| emissions | entity_code, date, series |
| carbon_intensity | entity_code, date |
| capacity | entity_code, date, series |

Business keys must be unique.

## Required fields

The following fields must not contain null values:

- entity
- entity_code
- date
- measurement columns

Where applicable:

- series
- is_aggregate_series

## Data types

Dates must be converted to date types.

Numeric measurements must be numeric.

Aggregate flags must be boolean.

## Aggregate series

Aggregate series must be preserved but must not be summed together
with their component series during analytical aggregation.

## Capacity dataset

Capacity is treated as a supplementary dataset.

Current observed coverage:

- 12 countries
- 2016-01-01 to 2026-08-01
- Offshore wind
- Onshore wind
- Solar
- Unknown wind
- Wind

Missing countries are not automatically considered data-quality failures.