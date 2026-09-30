WITH annual AS (
    SELECT
        t.geo_id,
        YEAR(t.date) AS year,
        t.value * 100 AS unemployment_rate_pct
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.BUREAU_OF_LABOR_STATISTICS_EMPLOYMENT_TIMESERIES t
    WHERE t.variable = 'Local_Area_Unemployment:_Unemployment_Rate,_Not_seasonally_adjusted,_Annual'
      AND t.geo_id IN ('geoId/C21780', 'geoId/18')
      AND YEAR(t.date) = 2025
)
SELECT
    a.geo_id,
    g.geo_name,
    a.year,
    a.unemployment_rate_pct
FROM annual a
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX g
  ON g.geo_id = a.geo_id
ORDER BY a.geo_id
