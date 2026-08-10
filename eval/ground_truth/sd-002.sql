-- Ground truth for eval/questions/single_domain.yaml#sd-002
-- PLACEHOLDER: table/column names not yet verified against a live account
-- (see scripts/setup_snowflake.py). Hand-verify before using this as a
-- correctness baseline — do not trust it as-is.

SELECT
    ts.value AS total_population
FROM SNOWFLAKE_PUBLIC_DATA_FREE.CYBERSYN.CENSUS_ACS_TIMESERIES ts
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.CYBERSYN.CENSUS_ACS_ATTRIBUTES attrs
    ON ts.variable = attrs.variable
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.CYBERSYN.GEOGRAPHY_INDEX geo
    ON ts.geo_id = geo.geo_id
WHERE attrs.variable_name = 'Total Population'
  AND geo.geo_name = 'Evansville, IN'
ORDER BY ts.date DESC
LIMIT 1;
