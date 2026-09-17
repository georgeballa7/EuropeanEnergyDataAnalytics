-- ============================================================
-- Leitfrage 1:
-- Wie haben sich Stromerzeugung und Stromnachfrage
-- in den untersuchten europäischen Ländern entwickelt?
--
-- Datenbasis:
-- Gold Layer / European Energy Analytics
-- ============================================================

WITH annual_generation AS (
    SELECT
        g.entity_code,
        d.year,
        SUM(g.generation_twh) AS generation_twh
    FROM european_energy_analytics.fact_generation AS g
    JOIN european_energy_analytics.dim_date AS d
        ON g.date = d.date
    JOIN european_energy_analytics.dim_energy_series AS s
        ON g.series_key = s.series_key
    WHERE s.is_aggregate_series = false
      AND d.year < YEAR(CURRENT_DATE)
    GROUP BY
        g.entity_code,
        d.year
),

annual_demand AS (
    SELECT
        d.entity_code,
        dt.year,
        SUM(d.demand_twh) AS demand_twh
    FROM european_energy_analytics.fact_demand AS d
    JOIN european_energy_analytics.dim_date AS dt
        ON d.date = dt.date
    WHERE dt.year < YEAR(CURRENT_DATE)
    GROUP BY
        d.entity_code,
        dt.year
)

SELECT
    c.country_name,
    g.entity_code,
    g.year,
    ROUND(g.generation_twh, 2) AS generation_twh,
    ROUND(d.demand_twh, 2) AS demand_twh,
    ROUND(g.generation_twh - d.demand_twh, 2) AS generation_demand_balance_twh
FROM annual_generation AS g
JOIN annual_demand AS d
    ON g.entity_code = d.entity_code
   AND g.year = d.year
JOIN european_energy_analytics.dim_country AS c
    ON g.entity_code = c.entity_code
ORDER BY
    c.country_name,
    g.year;