-- ============================================================
-- Leitfrage 2:
-- Wie hat sich der Stromerzeugungsmix im Zeitverlauf verändert?
--
-- Methodik:
-- - nur nicht-aggregierte Erzeugungsreihen
-- - Net Imports ausgeschlossen
-- - laufendes Kalenderjahr ausgeschlossen
-- - Analyse nach Land, Jahr und Energiekategorie
-- ============================================================

WITH annual_mix AS (
    SELECT
        g.entity_code,
        d.year,
        s.energy_category,
        SUM(g.generation_twh) AS generation_twh

    FROM european_energy_analytics.fact_generation AS g

    JOIN european_energy_analytics.dim_date AS d
        ON g.date = d.date

    JOIN european_energy_analytics.dim_energy_series AS s
        ON g.series_key = s.series_key

    WHERE s.is_aggregate_series = false
      AND s.series_name <> 'Net imports'
      AND d.year < YEAR(CURRENT_DATE)

    GROUP BY
        g.entity_code,
        d.year,
        s.energy_category
),

annual_total AS (
    SELECT
        entity_code,
        year,
        SUM(generation_twh) AS total_generation_twh
    FROM annual_mix
    GROUP BY
        entity_code,
        year
)

SELECT
    c.country_name,
    m.entity_code,
    m.year,
    m.energy_category,

    ROUND(m.generation_twh, 2)
        AS generation_twh,

    ROUND(
        100.0 * m.generation_twh
        / NULLIF(t.total_generation_twh, 0),
        1
    ) AS generation_share_pct

FROM annual_mix AS m

JOIN annual_total AS t
    ON m.entity_code = t.entity_code
   AND m.year = t.year

JOIN european_energy_analytics.dim_country AS c
    ON m.entity_code = c.entity_code

ORDER BY
    c.country_name,
    m.year,
    m.energy_category;