-- Q4: Installed Solar and Wind Capacity
-- Question:
-- How has installed solar and wind capacity evolved
-- across European countries?
--
-- Analysis period:
-- 2016 vs. 2025
--
-- Notes:
-- - Capacity data is available for 12 countries.
-- - Solar uses the non-aggregate "Solar" series.
-- - Total wind capacity uses the aggregate "Wind" series.
-- - Onshore, offshore and unknown wind are not added separately
--   in order to avoid double counting.
-- - 2026 is excluded because it is a partial year.

WITH annual_capacity AS (
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
        d.year IN (2016, 2025)
        AND s.series_name IN ('Solar', 'Wind')
    GROUP BY
        f.entity_code,
        d.year,
        s.series_name
),

comparison AS (
    SELECT
        c.entity_code,
        c.country_name,

        MAX(CASE
            WHEN a.year = 2016 AND a.series_name = 'Solar'
            THEN a.avg_capacity_gw
        END) AS solar_2016_gw,

        MAX(CASE
            WHEN a.year = 2025 AND a.series_name = 'Solar'
            THEN a.avg_capacity_gw
        END) AS solar_2025_gw,

        MAX(CASE
            WHEN a.year = 2016 AND a.series_name = 'Wind'
            THEN a.avg_capacity_gw
        END) AS wind_2016_gw,

        MAX(CASE
            WHEN a.year = 2025 AND a.series_name = 'Wind'
            THEN a.avg_capacity_gw
        END) AS wind_2025_gw

    FROM european_energy_analytics.dim_country AS c
    JOIN annual_capacity AS a
        ON c.entity_code = a.entity_code
    GROUP BY
        c.entity_code,
        c.country_name
)

SELECT
    country_name,

    ROUND(solar_2016_gw, 2) AS solar_2016_gw,
    ROUND(solar_2025_gw, 2) AS solar_2025_gw,

    ROUND(
        100.0 * (solar_2025_gw - solar_2016_gw)
        / NULLIF(solar_2016_gw, 0),
        1
    ) AS solar_change_pct,

    ROUND(wind_2016_gw, 2) AS wind_2016_gw,
    ROUND(wind_2025_gw, 2) AS wind_2025_gw,

    ROUND(
        100.0 * (wind_2025_gw - wind_2016_gw)
        / NULLIF(wind_2016_gw, 0),
        1
    ) AS wind_change_pct,

    ROUND(solar_2016_gw + wind_2016_gw, 2)
        AS solar_wind_2016_gw,

    ROUND(solar_2025_gw + wind_2025_gw, 2)
        AS solar_wind_2025_gw,

    ROUND(
        100.0 * (
            (solar_2025_gw + wind_2025_gw)
            - (solar_2016_gw + wind_2016_gw)
        )
        / NULLIF(solar_2016_gw + wind_2016_gw, 0),
        1
    ) AS solar_wind_change_pct

FROM comparison
WHERE
    solar_2016_gw IS NOT NULL
    AND solar_2025_gw IS NOT NULL
    AND wind_2016_gw IS NOT NULL
    AND wind_2025_gw IS NOT NULL
ORDER BY solar_wind_change_pct DESC;