-- Vilas County, WI (geoId/55125) ACS 5-year total-population change, 2019 to 2024.
-- Variable is B01003_001E_5YR (no vintage suffix in this extract); dates are year-end.
-- Criterion 007 pins 8.7.

WITH pop AS (
    SELECT
        MAX(CASE WHEN t.date = '2024-12-31' THEN t.value END) AS pop_2024,
        MAX(CASE WHEN t.date = '2019-12-31' THEN t.value END) AS pop_2019
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.AMERICAN_COMMUNITY_SURVEY_TIMESERIES t
    WHERE t.variable = 'B01003_001E_5YR'
      AND t.geo_id = 'geoId/55125'
      AND t.date IN ('2024-12-31', '2019-12-31')
)
SELECT ROUND(100.0 * (pop_2024 / NULLIF(pop_2019, 0) - 1), 1) AS pop_growth_5y_pct
FROM pop
