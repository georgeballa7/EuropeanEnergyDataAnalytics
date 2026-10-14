-- Q3: CO2 Emissions and Carbon Intensity
-- Question:
-- How did power-sector CO2 emissions and carbon intensity
-- change across European countries between 2019 and 2025?
--
-- Analysis period:
-- 2019 vs. 2025 (shared comparison years; both require 12 months)
--
-- Notes:
-- - Total emissions use the aggregate series "Total generation"
--   to avoid double counting individual generation technologies.
-- - Annual emissions are calculated as the sum of monthly MtCO2 values.
-- - Carbon intensity is calculated as the unweighted average of monthly gCO2/kWh values.
-- - Both comparison years must contain 12 months of observations.

WITH annual_emissions AS (
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
        AND d.year IN (2019, 2025)
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
        d.year IN (2019, 2025)
    GROUP BY
        f.entity_code,
        d.year
    HAVING COUNT(DISTINCT d.month_number) = 12
),

comparison AS (
    SELECT
        c.entity_code,
        c.country_name,

        MAX(CASE WHEN e.year = 2019
            THEN e.emissions_mtco2 END) AS emissions_2019_mtco2,
        MAX(CASE WHEN e.year = 2025
            THEN e.emissions_mtco2 END) AS emissions_2025_mtco2,

        MAX(CASE WHEN i.year = 2019
            THEN i.avg_carbon_intensity_gco2_per_kwh END)
            AS carbon_intensity_2019,

        MAX(CASE WHEN i.year = 2025
            THEN i.avg_carbon_intensity_gco2_per_kwh END)
            AS carbon_intensity_2025

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
    country_name,
    ROUND(emissions_2019_mtco2, 2) AS emissions_2019_mtco2,
    ROUND(emissions_2025_mtco2, 2) AS emissions_2025_mtco2,

    ROUND(
        100.0 * (emissions_2025_mtco2 - emissions_2019_mtco2)
        / NULLIF(emissions_2019_mtco2, 0),
        1
    ) AS emissions_change_pct,

    ROUND(carbon_intensity_2019, 1) AS carbon_intensity_2019,
    ROUND(carbon_intensity_2025, 1) AS carbon_intensity_2025,

    ROUND(
        carbon_intensity_2025 - carbon_intensity_2019,
        1
    ) AS carbon_intensity_change_gco2_per_kwh

FROM comparison
WHERE
    emissions_2019_mtco2 IS NOT NULL
    AND emissions_2025_mtco2 IS NOT NULL
    AND carbon_intensity_2019 IS NOT NULL
    AND carbon_intensity_2025 IS NOT NULL
ORDER BY emissions_change_pct;