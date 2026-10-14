-- Q3: CO2 Emissions and Carbon Intensity
-- Question:
-- How did power-sector CO2 emissions and carbon intensity
-- change across European countries between 2019 and the latest common complete year?
--
-- Analysis period:
-- 2019 vs. latest complete year available for both metrics
--
-- Notes:
-- - Total emissions use the aggregate series "Total generation"
--   to avoid double counting individual generation technologies.
-- - Annual emissions are calculated as the sum of monthly MtCO2 values.
-- - Carbon intensity is calculated as the unweighted average of monthly gCO2/kWh values.
-- - Both comparison years must contain 12 months of observations.

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
annual_emissions AS (
    SELECT
        f.entity_code,
        d.year,
        SUM(f.emissions_mtco2) AS emissions_mtco2
    FROM european_energy_analytics.fact_emissions AS f
    JOIN european_energy_analytics.dim_date AS d
        ON f.date = d.date
    JOIN european_energy_analytics.dim_energy_series AS s
        ON f.series_key = s.series_key
    WHERE
        s.series_name = 'Total generation'
        AND d.year IN ((SELECT start_year FROM comparison_period), (SELECT end_year FROM comparison_period))
    GROUP BY
        f.entity_code,
        d.year
    HAVING COUNT(DISTINCT d.month_number) = 12
),

annual_intensity AS (
    SELECT
        f.entity_code,
        d.year,
        AVG(f.emissions_intensity_gco2_per_kwh)
            AS avg_carbon_intensity_gco2_per_kwh
    FROM european_energy_analytics.fact_carbon_intensity AS f
    JOIN european_energy_analytics.dim_date AS d
        ON f.date = d.date
    WHERE
        d.year IN ((SELECT start_year FROM comparison_period), (SELECT end_year FROM comparison_period))
    GROUP BY
        f.entity_code,
        d.year
    HAVING COUNT(DISTINCT d.month_number) = 12
),

comparison AS (
    SELECT
        c.entity_code,
        c.country_name,

        MAX(CASE WHEN e.year = (SELECT start_year FROM comparison_period)
            THEN e.emissions_mtco2 END) AS emissions_start_mtco2,
        MAX(CASE WHEN e.year = (SELECT end_year FROM comparison_period)
            THEN e.emissions_mtco2 END) AS emissions_end_mtco2,

        MAX(CASE WHEN i.year = (SELECT start_year FROM comparison_period)
            THEN i.avg_carbon_intensity_gco2_per_kwh END)
            AS carbon_intensity_start,

        MAX(CASE WHEN i.year = (SELECT end_year FROM comparison_period)
            THEN i.avg_carbon_intensity_gco2_per_kwh END)
            AS carbon_intensity_end

    FROM european_energy_analytics.dim_country AS c
    LEFT JOIN annual_emissions AS e
        ON c.entity_code = e.entity_code
    LEFT JOIN annual_intensity AS i
        ON c.entity_code = i.entity_code
    GROUP BY
        c.entity_code,
        c.country_name
)

SELECT
    (SELECT start_year FROM comparison_period) AS start_year,
    (SELECT end_year FROM comparison_period) AS end_year,
    country_name,
    ROUND(emissions_start_mtco2, 2) AS emissions_start_mtco2,
    ROUND(emissions_end_mtco2, 2) AS emissions_end_mtco2,

    ROUND(
        100.0 * (emissions_end_mtco2 - emissions_start_mtco2)
        / NULLIF(emissions_start_mtco2, 0),
        1
    ) AS emissions_change_pct,

    ROUND(carbon_intensity_start, 1) AS carbon_intensity_start,
    ROUND(carbon_intensity_end, 1) AS carbon_intensity_end,

    ROUND(
        carbon_intensity_end - carbon_intensity_start,
        1
    ) AS carbon_intensity_change_gco2_per_kwh

FROM comparison
WHERE
    emissions_start_mtco2 IS NOT NULL
    AND emissions_end_mtco2 IS NOT NULL
    AND carbon_intensity_start IS NOT NULL
    AND carbon_intensity_end IS NOT NULL
ORDER BY emissions_change_pct;