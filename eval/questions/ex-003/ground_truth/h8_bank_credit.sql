-- Latest H.8 weekly seasonally adjusted bank credit, all commercial banks.
-- FINANCIAL_ECONOMIC_INDICATORS, not FEDERAL_RESERVE (that weekly catalog is commercial paper).

SELECT
    t.geo_id,
    t.date,
    t.value AS bank_credit_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_ECONOMIC_INDICATORS_TIMESERIES t
WHERE t.variable = 'H8B1001NCBA_SA'
QUALIFY t.date = MAX(t.date) OVER ()
