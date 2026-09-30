-- H.8 weekly SA industry levels used in a Treasury benchmark vs own-bank growth.
-- All commercial banks panel. Values in USD.

SELECT
    a.variable,
    a.variable_name,
    t.date,
    t.value
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_ECONOMIC_INDICATORS_TIMESERIES t
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FINANCIAL_ECONOMIC_INDICATORS_ATTRIBUTES a
  ON a.variable = t.variable
WHERE t.variable IN (
    'H8B1001NCBA_SA',  -- bank credit
    'H8B1020NCBA_SA',  -- loans and leases in bank credit
    'H8B1058NCBA_SA'   -- deposits
)
QUALIFY t.date = MAX(t.date) OVER (PARTITION BY t.variable)
ORDER BY a.variable
