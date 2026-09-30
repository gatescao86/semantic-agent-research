-- Renasant Bank (FDIC cert 12437) branch deposits by state.
-- FDIC Summary of Deposits 2025-06-30, DEPSUMBR. Values in USD thousands.
-- Criterion 011 pins SUM(deposits) = 21,199,259.
-- Criterion 019 pins SUM(n_branches) = 253.
-- Criterion 018 pins Mississippi / that total = 40.2%.

SELECT
    g.geo_name AS state,
    COUNT(*) AS n_branches,
    ROUND(SUM(t.value), 0) AS deposits
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
  ON t.fdic_branch_id = b.fdic_branch_id
 AND t.fdic_institution_id = b.fdic_institution_id
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX g
  ON g.geo_id = b.geo_id_state
WHERE b.fdic_institution_certificate_number = '12437'
  AND t.variable = 'DEPSUMBR'
  AND t.date = '2025-06-30'
GROUP BY g.geo_name
ORDER BY deposits DESC
