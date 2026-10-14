-- Q4: Installed Solar and Wind Capacity
-- Question:
-- How has installed solar and wind capacity evolved
-- across European countries?
--
-- Analysis period:
-- 2019 vs. latest complete year available for solar and wind
--
-- Notes:
-- - Country coverage is determined by complete observations in both comparison years.
-- - Solar uses the non-aggregate "Solar" series.
-- - Total wind capacity uses the aggregate "Wind" series.
-- - Onshore, offshore and unknown wind are not added separately
--   in order to avoid double counting.
-- - Current calendar year is excluded; future complete years are selected automatically.

WITH comparison_period AS (
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
    ORDER BY end_year DESC
    LIMIT 1
),
annual_capacity AS (
    SELECT
        f.entity_code,
        d.year,
        s.series_name,
        AVG(f.capacity_gw) AS avg_capacity_gw
    FROM european_energy_analytics.fact_capacity AS f
    JOIN european_energy_analytics.dim_date AS d
        ON f.date = d.date
    JOIN european_energy_analytics.dim_capacity_series AS s
        ON f.capacity_series_key = s.capacity_series_key
    WHERE
        d.year IN ((SELECT start_year FROM comparison_period), (SELECT end_year FROM comparison_period))
        AND s.series_name IN ('Solar', 'Wind')
    GROUP BY
        f.entity_code,
        d.year,
        s.series_name
    HAVING COUNT(DISTINCT d.month_number) = 12
),

comparison AS (
    SELECT
        c.entity_code,
        c.country_name,

        MAX(CASE
            WHEN a.year = (SELECT start_year FROM comparison_period) AND a.series_name = 'Solar'
            THEN a.avg_capacity_gw
        END) AS solar_start_gw,

        MAX(CASE
            WHEN a.year = (SELECT end_year FROM comparison_period) AND a.series_name = 'Solar'
            THEN a.avg_capacity_gw
        END) AS solar_end_gw,

        MAX(CASE
            WHEN a.year = (SELECT start_year FROM comparison_period) AND a.series_name = 'Wind'
            THEN a.avg_capacity_gw
        END) AS wind_start_gw,

        MAX(CASE
            WHEN a.year = (SELECT end_year FROM comparison_period) AND a.series_name = 'Wind'
            THEN a.avg_capacity_gw
        END) AS wind_end_gw

    FROM european_energy_analytics.dim_country AS c
    JOIN annual_capacity AS a
        ON c.entity_code = a.entity_code
    GROUP BY
        c.entity_code,
        c.country_name
)

SELECT
    (SELECT start_year FROM comparison_period) AS start_year,
    (SELECT end_year FROM comparison_period) AS end_year,
    country_name,

    ROUND(solar_start_gw, 2) AS solar_start_gw,
    ROUND(solar_end_gw, 2) AS solar_end_gw,

    ROUND(
        100.0 * (solar_end_gw - solar_start_gw)
        / NULLIF(solar_start_gw, 0),
        1
    ) AS solar_change_pct,

    ROUND(wind_start_gw, 2) AS wind_start_gw,
    ROUND(wind_end_gw, 2) AS wind_end_gw,

    ROUND(
        100.0 * (wind_end_gw - wind_start_gw)
        / NULLIF(wind_start_gw, 0),
        1
    ) AS wind_change_pct,

    ROUND(solar_start_gw + wind_start_gw, 2)
        AS solar_wind_start_gw,

    ROUND(solar_end_gw + wind_end_gw, 2)
        AS solar_wind_end_gw,

    ROUND(
        100.0 * (
            (solar_end_gw + wind_end_gw)
            - (solar_start_gw + wind_start_gw)
        )
        / NULLIF(solar_start_gw + wind_start_gw, 0),
        1
    ) AS solar_wind_change_pct

FROM comparison
WHERE
    solar_start_gw IS NOT NULL
    AND solar_end_gw IS NOT NULL
    AND wind_start_gw IS NOT NULL
    AND wind_end_gw IS NOT NULL
ORDER BY solar_wind_change_pct DESC;