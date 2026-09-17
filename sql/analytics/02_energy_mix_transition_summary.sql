-- ============================================================
-- Leitfrage 2 – Summary:
-- Wie hat sich der Stromerzeugungsmix im Zeitverlauf verändert?
--
-- Methodik:
-- - 20 analysierte Länder
-- - nur nicht-aggregierte Erzeugungsreihen
-- - Net Imports ausgeschlossen
-- - nur vollständige Kalenderjahre
-- - gemeinsamer Vergleichszeitraum aller Länder
-- - laufendes Kalenderjahr ausgeschlossen
-- - Veränderung der Mix-Anteile in Prozentpunkten
-- ============================================================

WITH monthly_mix AS (
    SELECT
        g.entity_code,
        g.date,
        s.energy_category,
        SUM(g.generation_twh) AS generation_twh

    FROM european_energy_analytics.fact_generation AS g

    JOIN european_energy_analytics.dim_energy_series AS s
        ON g.series_key = s.series_key

    WHERE s.is_aggregate_series = false
      AND s.series_name <> 'Net imports'

    GROUP BY
        g.entity_code,
        g.date,
        s.energy_category
),

annual_mix AS (
    SELECT
        m.entity_code,
        d.year,
        m.energy_category,
        COUNT(DISTINCT d.month_number) AS months_available,
        SUM(m.generation_twh) AS generation_twh

    FROM monthly_mix AS m

    JOIN european_energy_analytics.dim_date AS d
        ON m.date = d.date

    WHERE d.year < YEAR(CURRENT_DATE)

    GROUP BY
        m.entity_code,
        d.year,
        m.energy_category
),

-- Ein Jahr gilt als vollständig, wenn für das Land
-- insgesamt 12 unterschiedliche Monate vorhanden sind.
complete_country_years AS (
    SELECT
        entity_code,
        year

    FROM (
        SELECT
            g.entity_code,
            d.year,
            COUNT(DISTINCT d.month_number) AS months_available

        FROM european_energy_analytics.fact_generation AS g

        JOIN european_energy_analytics.dim_date AS d
            ON g.date = d.date

        WHERE d.year < YEAR(CURRENT_DATE)

        GROUP BY
            g.entity_code,
            d.year
    )

    WHERE months_available = 12
),

annual_total AS (
    SELECT
        m.entity_code,
        m.year,
        SUM(m.generation_twh) AS total_generation_twh

    FROM annual_mix AS m

    JOIN complete_country_years AS cy
        ON m.entity_code = cy.entity_code
       AND m.year = cy.year

    GROUP BY
        m.entity_code,
        m.year
),

annual_shares AS (
    SELECT
        m.entity_code,
        m.year,
        m.energy_category,

        100.0 * m.generation_twh
            / NULLIF(t.total_generation_twh, 0)
            AS generation_share_pct

    FROM annual_mix AS m

    JOIN annual_total AS t
        ON m.entity_code = t.entity_code
       AND m.year = t.year
),

country_coverage AS (
    SELECT
        entity_code,
        MIN(year) AS first_complete_year,
        MAX(year) AS last_complete_year

    FROM annual_total

    GROUP BY entity_code
),

common_period AS (
    SELECT
        MAX(first_complete_year) AS common_start_year,
        MIN(last_complete_year) AS common_end_year

    FROM country_coverage
),

comparison AS (
    SELECT
        s.entity_code,
        p.common_start_year,
        p.common_end_year,

        MAX(
            CASE
                WHEN s.year = p.common_start_year
                     AND s.energy_category = 'Renewable'
                THEN s.generation_share_pct
            END
        ) AS renewable_start_pct,

        MAX(
            CASE
                WHEN s.year = p.common_end_year
                     AND s.energy_category = 'Renewable'
                THEN s.generation_share_pct
            END
        ) AS renewable_end_pct,

        MAX(
            CASE
                WHEN s.year = p.common_start_year
                     AND s.energy_category = 'Fossil'
                THEN s.generation_share_pct
            END
        ) AS fossil_start_pct,

        MAX(
            CASE
                WHEN s.year = p.common_end_year
                     AND s.energy_category = 'Fossil'
                THEN s.generation_share_pct
            END
        ) AS fossil_end_pct,

        MAX(
            CASE
                WHEN s.year = p.common_start_year
                     AND s.energy_category = 'Clean'
                THEN s.generation_share_pct
            END
        ) AS clean_start_pct,

        MAX(
            CASE
                WHEN s.year = p.common_end_year
                     AND s.energy_category = 'Clean'
                THEN s.generation_share_pct
            END
        ) AS clean_end_pct

    FROM annual_shares AS s

    CROSS JOIN common_period AS p

    WHERE s.year IN (
        p.common_start_year,
        p.common_end_year
    )

    GROUP BY
        s.entity_code,
        p.common_start_year,
        p.common_end_year
)

SELECT
    c.country_name,
    x.entity_code,

    x.common_start_year,
    x.common_end_year,

    ROUND(x.renewable_start_pct, 1)
        AS renewable_start_pct,

    ROUND(x.renewable_end_pct, 1)
        AS renewable_end_pct,

    ROUND(
        x.renewable_end_pct - x.renewable_start_pct,
        1
    ) AS renewable_change_pp,

    ROUND(x.fossil_start_pct, 1)
        AS fossil_start_pct,

    ROUND(x.fossil_end_pct, 1)
        AS fossil_end_pct,

    ROUND(
        x.fossil_end_pct - x.fossil_start_pct,
        1
    ) AS fossil_change_pp,

    ROUND(x.clean_start_pct, 1)
        AS clean_start_pct,

    ROUND(x.clean_end_pct, 1)
        AS clean_end_pct,

    ROUND(
        x.clean_end_pct - x.clean_start_pct,
        1
    ) AS clean_change_pp

FROM comparison AS x

JOIN european_energy_analytics.dim_country AS c
    ON x.entity_code = c.entity_code

ORDER BY c.country_name;