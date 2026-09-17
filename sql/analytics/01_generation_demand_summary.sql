-- ============================================================
-- Leitfrage 1 – Summary:
-- Entwicklung von Stromerzeugung und Stromnachfrage
-- vom ersten verfügbaren Jahr bis zum letzten vollständigen Jahr
-- ============================================================

WITH annual_generation AS (
    SELECT
        g.entity_code,
        d.year,

        SUM(
            CASE
                WHEN s.is_aggregate_series = false
                     AND s.series_name <> 'Net imports'
                THEN g.generation_twh
                ELSE 0
            END
        ) AS domestic_generation_twh,

        SUM(
            CASE
                WHEN s.series_name = 'Net imports'
                THEN g.generation_twh
                ELSE 0
            END
        ) AS net_imports_twh

    FROM european_energy_analytics.fact_generation AS g

    JOIN european_energy_analytics.dim_date AS d
        ON g.date = d.date

    JOIN european_energy_analytics.dim_energy_series AS s
        ON g.series_key = s.series_key

    WHERE d.year < YEAR(CURRENT_DATE)

    GROUP BY
        g.entity_code,
        d.year
),

annual_demand AS (
    SELECT
        f.entity_code,
        d.year,
        SUM(f.demand_twh) AS demand_twh

    FROM european_energy_analytics.fact_demand AS f

    JOIN european_energy_analytics.dim_date AS d
        ON f.date = d.date

    WHERE d.year < YEAR(CURRENT_DATE)

    GROUP BY
        f.entity_code,
        d.year
),

annual_data AS (
    SELECT
        g.entity_code,
        g.year,
        g.domestic_generation_twh,
        g.net_imports_twh,
        d.demand_twh

    FROM annual_generation AS g

    JOIN annual_demand AS d
        ON g.entity_code = d.entity_code
       AND g.year = d.year
),

country_period AS (
    SELECT
        entity_code,
        MIN(year) AS first_year,
        MAX(year) AS latest_year
    FROM annual_data
    GROUP BY entity_code
)

SELECT
    c.country_name,
    p.entity_code,

    p.first_year,
    p.latest_year,

    ROUND(first_data.domestic_generation_twh, 2)
        AS first_generation_twh,

    ROUND(latest_data.domestic_generation_twh, 2)
        AS latest_generation_twh,

    ROUND(
        100.0 *
        (
            latest_data.domestic_generation_twh
            - first_data.domestic_generation_twh
        )
        / NULLIF(first_data.domestic_generation_twh, 0),
        1
    ) AS generation_change_pct,

    ROUND(first_data.demand_twh, 2)
        AS first_demand_twh,

    ROUND(latest_data.demand_twh, 2)
        AS latest_demand_twh,

    ROUND(
        100.0 *
        (latest_data.demand_twh - first_data.demand_twh)
        / NULLIF(first_data.demand_twh, 0),
        1
    ) AS demand_change_pct,

    ROUND(first_data.net_imports_twh, 2)
        AS first_net_imports_twh,

    ROUND(latest_data.net_imports_twh, 2)
        AS latest_net_imports_twh

FROM country_period AS p

JOIN annual_data AS first_data
    ON p.entity_code = first_data.entity_code
   AND p.first_year = first_data.year

JOIN annual_data AS latest_data
    ON p.entity_code = latest_data.entity_code
   AND p.latest_year = latest_data.year

JOIN european_energy_analytics.dim_country AS c
    ON p.entity_code = c.entity_code

ORDER BY c.country_name;