-- Evansville four-county deposit market (CBSA geoId/C21780 counties).
-- Vanderburgh, Warrick, Posey IN and Henderson KY.
-- FDIC Summary of Deposits, branch deposits (DEPSUMBR). Values in USD.

WITH cbsa_counties AS (
    SELECT column1 AS geo_id_county
    FROM VALUES ('geoId/18163'), ('geoId/18173'), ('geoId/18129'), ('geoId/21101')
),
branch_deposits AS (
    SELECT
        b.institution_name,
        t.date,
        t.value AS branch_deposits
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
    JOIN cbsa_counties c
      ON c.geo_id_county = b.geo_id_county
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
      ON t.fdic_branch_id = b.fdic_branch_id
     AND t.fdic_institution_id = b.fdic_institution_id
    WHERE t.variable = 'DEPSUMBR'
      AND t.date IN ('2024-06-30', '2025-06-30')
),
by_institution AS (
    SELECT
        institution_name,
        date,
        SUM(branch_deposits) AS deposits
    FROM branch_deposits
    GROUP BY institution_name, date
)
SELECT
    institution_name,
    date,
    deposits,
    ROUND(100.0 * deposits / SUM(deposits) OVER (PARTITION BY date), 2) AS market_share_pct,
    ROUND(SUM(deposits) OVER (PARTITION BY date), 0) AS total_market_deposits,
    ROUND(
        100.0 * (deposits - LAG(deposits) OVER (PARTITION BY institution_name ORDER BY date))
        / NULLIF(LAG(deposits) OVER (PARTITION BY institution_name ORDER BY date), 0),
        1
    ) AS yoy_pct
FROM by_institution
ORDER BY date DESC, deposits DESC
