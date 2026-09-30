-- Latest H.8 weekly SA loans and leases in bank credit, all commercial banks.
-- H8B1020NCBA_SA. USD.

SELECT t.geo_id, t.date, t.value AS loans_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_ECONOMIC_INDICATORS_TIMESERIES t
WHERE t.variable = 'H8B1020NCBA_SA'
QUALIFY t.date = MAX(t.date) OVER ()
