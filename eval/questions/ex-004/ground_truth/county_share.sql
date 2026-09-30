-- Forward Bank (cert 28530) in-market deposit share by footprint county.
-- FDIC Summary of Deposits 2025-06-30, DEPSUMBR. Values in USD thousands.
-- Authoring for criterion 002/006: Vilas is the required underweight hit
-- (0.5% share). Other thin-and-growing: Oneida 0.7%, Marathon 1.6%,
-- Chippewa 3.6%. Core foils: Clark 35.5%, Price 47.5%, Taylor 17.5%.

WITH fwd AS (
    SELECT
        b.geo_id_county,
        COUNT(*) AS fwd_branches,
        SUM(t.value) AS fwd_deposits
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
      ON t.fdic_branch_id = b.fdic_branch_id
     AND t.fdic_institution_id = b.fdic_institution_id
    WHERE b.fdic_institution_certificate_number = '28530'
      AND t.variable = 'DEPSUMBR'
      AND t.date = '2025-06-30'
    GROUP BY 1
),
mkt AS (
    SELECT
        b.geo_id_county,
        SUM(t.value) AS market_deposits
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
      ON t.fdic_branch_id = b.fdic_branch_id
     AND t.fdic_institution_id = b.fdic_institution_id
    JOIN fwd f
      ON f.geo_id_county = b.geo_id_county
    WHERE t.variable = 'DEPSUMBR'
      AND t.date = '2025-06-30'
    GROUP BY 1
)
SELECT
    g.geo_name AS county,
    f.fwd_branches,
    ROUND(f.fwd_deposits, 0) AS fwd_deposits,
    ROUND(m.market_deposits, 0) AS market_deposits,
    ROUND(100.0 * f.fwd_deposits / NULLIF(m.market_deposits, 0), 1) AS share_pct
FROM fwd f
JOIN mkt m
  ON m.geo_id_county = f.geo_id_county
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX g
  ON g.geo_id = f.geo_id_county
ORDER BY share_pct ASC
