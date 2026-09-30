-- United Community Bank, Greenville SC (id_rssd 1017939). Call-report DEP. USD.

SELECT t.date, t.value AS deposits_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_INSTITUTION_TIMESERIES t
WHERE t.id_rssd = 1017939
  AND t.variable = 'DEP'
QUALIFY t.date = MAX(t.date) OVER ()
