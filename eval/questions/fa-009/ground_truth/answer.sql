-- Latest H.8 weekly SA deposits, all commercial banks. H8B1058NCBA_SA. USD.

SELECT t.geo_id, t.date, t.value AS deposits_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_ECONOMIC_INDICATORS_TIMESERIES t
WHERE t.variable = 'H8B1058NCBA_SA'
QUALIFY t.date = MAX(t.date) OVER ()
