-- H.8 weekly SA bank credit, all commercial banks, extract vintage 2026-05-20.
-- Variable H8B1001NCBA_SA. Values in USD. Do not use live MAX(date).

SELECT
    t.geo_id,
    t.date,
    t.value AS bank_credit_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_ECONOMIC_INDICATORS_TIMESERIES t
WHERE t.variable = 'H8B1001NCBA_SA'
  AND t.date = '2026-05-20'
