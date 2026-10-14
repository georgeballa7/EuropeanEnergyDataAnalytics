-- ============================================================
-- Leitfrage 1 – Summary:
-- Entwicklung von Stromerzeugung und Stromnachfrage
-- Vergleich 2019 mit dem jüngsten vollständigen Datenjahr
-- Nur Länder mit vollständiger Erzeugung und Nachfrage in beiden Jahren
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
    HAVING COUNT(DISTINCT d.month_number) = 12
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
    HAVING COUNT(DISTINCT d.month_number) = 12
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

comparison_period AS (
    -- One shared rule across all four analytical comparisons.
    -- Require a complete calendar year in every source dataset.
    SELECT 2019 AS start_year, MAX(year) AS end_year
    FROM (
        SELECT d.year, 'generation' AS source_name, COUNT(DISTINCT d.month_number) AS months
        FROM european_energy_analytics.fact_generation f JOIN european_energy_analytics.dim_date d ON f.date = d.date
        GROUP BY d.year
        UNION ALL
        SELECT d.year, 'demand', COUNT(DISTINCT d.month_number)
        FROM european_energy_analytics.fact_demand f JOIN european_energy_analytics.dim_date d ON f.date = d.date
        GROUP BY d.year
        UNION ALL
        SELECT d.year, 'emissions', COUNT(DISTINCT d.month_number)
        FROM european_energy_analytics.fact_emissions f JOIN european_energy_analytics.dim_date d ON f.date = d.date
        GROUP BY d.year
        UNION ALL
        SELECT d.year, 'carbon_intensity', COUNT(DISTINCT d.month_number)
        FROM european_energy_analytics.fact_carbon_intensity f JOIN european_energy_analytics.dim_date d ON f.date = d.date
        GROUP BY d.year
        UNION ALL
        SELECT d.year, 'solar_capacity', COUNT(DISTINCT d.month_number)
        FROM european_energy_analytics.fact_capacity f
        JOIN european_energy_analytics.dim_date d ON f.date = d.date
        JOIN european_energy_analytics.dim_capacity_series s ON f.capacity_series_key = s.capacity_series_key
        WHERE s.series_name = 'Solar'
        GROUP BY d.year
        UNION ALL
        SELECT d.year, 'wind_capacity', COUNT(DISTINCT d.month_number)
        FROM european_energy_analytics.fact_capacity f
        JOIN european_energy_analytics.dim_date d ON f.date = d.date
        JOIN european_energy_analytics.dim_capacity_series s ON f.capacity_series_key = s.capacity_series_key
        WHERE s.series_name = 'Wind'
        GROUP BY d.year
    ) AS coverage
    WHERE year >= 2019 AND year < YEAR(CURRENT_DATE) AND months = 12
    GROUP BY year
    HAVING COUNT(DISTINCT source_name) = 6
),

country_period AS (
    SELECT
        a.entity_code,
        p.start_year,
        p.end_year
    FROM annual_data AS a
    CROSS JOIN comparison_period AS p
    WHERE a.year IN (p.start_year, p.end_year)
    GROUP BY a.entity_code, p.start_year, p.end_year
    HAVING COUNT(DISTINCT a.year) = 2
)

SELECT
    c.country_name,
    p.entity_code,

    p.start_year,
    p.end_year,

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
   AND p.start_year = first_data.year

JOIN annual_data AS latest_data
    ON p.entity_code = latest_data.entity_code
   AND p.end_year = latest_data.year

JOIN european_energy_analytics.dim_country AS c
    ON p.entity_code = c.entity_code

ORDER BY c.country_name;