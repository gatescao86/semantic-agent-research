-- Renasant share vs the rest of the market in core and thin CBSAs.
-- Atlanta (C12060), Tupelo (C46180), Jackson (C27140), Memphis (C32820).
-- FDIC Summary of Deposits 2025-06-30, DEPSUMBR. Values in USD thousands.
-- Criterion 012 pins Tupelo deposits = 2,145,463.

WITH cbsas AS (
    SELECT column1 AS geo_id_cbsa
    FROM VALUES ('geoId/C12060'), ('geoId/C46180'), ('geoId/C27140'), ('geoId/C32820')
),
mkt AS (
    SELECT
        g.geo_name,
        b.fdic_institution_certificate_number AS cert,
        b.institution_name,
        SUM(t.value) AS deposits
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
    JOIN cbsas c
      ON c.geo_id_cbsa = b.geo_id_cbsa
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX g
      ON g.geo_id = b.geo_id_cbsa
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
      ON t.fdic_branch_id = b.fdic_branch_id
     AND t.fdic_institution_id = b.fdic_institution_id
    WHERE t.variable = 'DEPSUMBR'
      AND t.date = '2025-06-30'
    GROUP BY 1, 2, 3
)
SELECT
    geo_name,
    institution_name,
    cert,
    ROUND(deposits, 0) AS deposits,
    ROUND(100.0 * deposits / SUM(deposits) OVER (PARTITION BY geo_name), 1) AS share_pct,
    ROUND(SUM(deposits) OVER (PARTITION BY geo_name), 0) AS market_deposits
FROM mkt
QUALIFY ROW_NUMBER() OVER (PARTITION BY geo_name ORDER BY deposits DESC) <= 5
     OR cert = '12437'
ORDER BY geo_name, deposits DESC
