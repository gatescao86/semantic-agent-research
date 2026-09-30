-- Evansville CBSA (geoId/C21780) annual LAUS unemployment rate, NSA, 2025.
-- Stored as a fraction; returned in percent.

SELECT ROUND(t.value * 100, 1) AS unemployment_rate_pct
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.BUREAU_OF_LABOR_STATISTICS_EMPLOYMENT_TIMESERIES t
WHERE t.variable = 'Local_Area_Unemployment:_Unemployment_Rate,_Not_seasonally_adjusted,_Annual'
  AND t.geo_id = 'geoId/C21780'
  AND YEAR(t.date) = 2025
