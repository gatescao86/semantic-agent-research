-- Renasant Bank (cert 12437) deposit share, Tupelo, MS micro area. DEPSUMBR. Share in percent.

WITH mkt AS (
    SELECT
        b.fdic_institution_certificate_number AS cert,
        SUM(t.value) AS deposits
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
      ON t.fdic_branch_id = b.fdic_branch_id
     AND t.fdic_institution_id = b.fdic_institution_id
    WHERE b.geo_id_cbsa = 'geoId/C46180'
      AND t.variable = 'DEPSUMBR'
      AND t.date = (
        SELECT MAX(date)
        FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES
        WHERE variable = 'DEPSUMBR'
    )
    GROUP BY 1
)
SELECT ROUND(100.0 * SUM(IFF(cert = '12437', deposits, 0)) / SUM(deposits), 4) AS share_pct
FROM mkt
