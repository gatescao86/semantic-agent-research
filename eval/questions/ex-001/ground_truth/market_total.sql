-- Evansville, IN-KY metro. Census/Data Commons CBSA geo_id (OMB 21780).
-- DEPSUMBR. Values in USD thousands. Extract vintage 2025-06-30.
-- Same gold as eval/questions/fa-002/ground_truth/answer.sql.

SELECT ROUND(SUM(t.value), 0) AS total_deposits
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
  ON t.fdic_branch_id = b.fdic_branch_id
 AND t.fdic_institution_id = b.fdic_institution_id
WHERE b.geo_id_cbsa = 'geoId/C21780'
  AND t.variable = 'DEPSUMBR'
  AND t.date = '2025-06-30'
