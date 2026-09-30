-- United Community Bank, Greenville SC (id_rssd 1017939, fdic_cert 16889).
-- Institution call-report stocks. Not FDIC Summary of Deposits.
-- Values in USD.

SELECT
    t.variable,
    a.variable_name,
    t.date,
    t.value
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_INSTITUTION_TIMESERIES t
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_INSTITUTION_ATTRIBUTES a
  ON a.variable = t.variable
WHERE t.id_rssd = 1017939
  AND t.variable IN ('ASSET', 'DEP', 'LNLSGR', 'LNLSNET', 'SC')
  AND t.date >= '2024-12-31'
ORDER BY t.variable, t.date
