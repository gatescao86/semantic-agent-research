-- ACS 5-year change for Forward Bank thin-and-growing footprint counties.
-- Population: B01003_001E_5YR at year-end (no vintage suffix in this extract).
-- Income: B19013_001E_5YR_YYYY (vintage suffix). Dates 2019-12-31 and 2024-12-31.
-- Authoring for criterion 005. Not a single-value pin.

WITH geos AS (
    SELECT column1 AS geo_id, column2 AS county
    FROM VALUES
        ('geoId/55125', 'Vilas'),
        ('geoId/55085', 'Oneida'),
        ('geoId/55017', 'Chippewa'),
        ('geoId/55073', 'Marathon')
),
pop AS (
    SELECT
        geo_id,
        MAX(CASE WHEN date = '2024-12-31' THEN value END) AS pop_2024,
        MAX(CASE WHEN date = '2019-12-31' THEN value END) AS pop_2019
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.AMERICAN_COMMUNITY_SURVEY_TIMESERIES
    WHERE variable = 'B01003_001E_5YR'
      AND date IN ('2024-12-31', '2019-12-31')
    GROUP BY 1
),
inc AS (
    SELECT
        g.geo_id,
        i19.value AS mhi_2019,
        i24.value AS mhi_2024
    FROM geos g
    LEFT JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.AMERICAN_COMMUNITY_SURVEY_TIMESERIES i24
      ON i24.geo_id = g.geo_id
     AND i24.variable = 'B19013_001E_5YR_2024'
     AND i24.date = '2024-12-31'
    LEFT JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.AMERICAN_COMMUNITY_SURVEY_TIMESERIES i19
      ON i19.geo_id = g.geo_id
     AND i19.variable = 'B19013_001E_5YR_2019'
     AND i19.date = '2019-12-31'
)
SELECT
    g.county,
    ROUND(100.0 * (p.pop_2024 / NULLIF(p.pop_2019, 0) - 1), 1) AS pop_growth_5y_pct,
    ROUND(i.mhi_2024, 0) AS mhi_2024,
    ROUND(100.0 * (i.mhi_2024 / NULLIF(i.mhi_2019, 0) - 1), 1) AS mhi_growth_5y_pct
FROM geos g
LEFT JOIN pop p ON p.geo_id = g.geo_id
LEFT JOIN inc i ON i.geo_id = g.geo_id
ORDER BY g.county
