-- Evansville CBSA (geoId/C21780) ACS 5-year 2024 median household income.

SELECT ROUND(t.value, 0) AS median_hh_income_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.AMERICAN_COMMUNITY_SURVEY_TIMESERIES t
WHERE t.variable = 'B19013_001E_5YR_2024'
  AND t.geo_id = 'geoId/C21780'
