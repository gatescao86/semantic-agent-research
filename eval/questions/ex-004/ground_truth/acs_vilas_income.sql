-- Vilas County, WI (geoId/55125) ACS 5-year median household income change.
-- Variable uses a vintage suffix in this extract: B19013_001E_5YR_YYYY.
-- Criterion 008 pins 45.4.

SELECT ROUND(100.0 * (i24.value / NULLIF(i19.value, 0) - 1), 1) AS mhi_growth_5y_pct
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.AMERICAN_COMMUNITY_SURVEY_TIMESERIES i24
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.AMERICAN_COMMUNITY_SURVEY_TIMESERIES i19
  ON i19.geo_id = i24.geo_id
WHERE i24.geo_id = 'geoId/55125'
  AND i24.variable = 'B19013_001E_5YR_2024'
  AND i24.date = '2024-12-31'
  AND i19.variable = 'B19013_001E_5YR_2019'
  AND i19.date = '2019-12-31'
