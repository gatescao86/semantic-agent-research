-- Renasant Bank (cert 12437) branch deposits in Mississippi. DEPSUMBR. USD thousands.

SELECT ROUND(SUM(t.value), 0) AS deposits
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
  ON t.fdic_branch_id = b.fdic_branch_id
 AND t.fdic_institution_id = b.fdic_institution_id
WHERE b.fdic_institution_certificate_number = '12437'
  AND b.geo_id_state = 'geoId/28'
  AND t.variable = 'DEPSUMBR'
  AND t.date = (
        SELECT MAX(date)
        FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES
        WHERE variable = 'DEPSUMBR'
    )
