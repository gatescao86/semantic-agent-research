-- Ground truth for eval/questions/single_domain.yaml#sd-001
-- PLACEHOLDER: table/column names not yet verified against a live account
-- (see scripts/setup_snowflake.py). Hand-verify before using this as a
-- correctness baseline — do not trust it as-is.

SELECT
    ts.date,
    ts.value AS mortgage_rate
FROM SNOWFLAKE_PUBLIC_DATA_FREE.CYBERSYN.FINANCIAL_ECONOMIC_INDICATOR_TIMESERIES ts
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.CYBERSYN.FINANCIAL_ECONOMIC_INDICATOR_ATTRIBUTES attrs
    ON ts.variable = attrs.variable
WHERE attrs.variable_name = '30-Year Fixed Rate Mortgage Average'
  AND ts.date >= DATEADD(quarter, -4, CURRENT_DATE())
ORDER BY ts.date;
