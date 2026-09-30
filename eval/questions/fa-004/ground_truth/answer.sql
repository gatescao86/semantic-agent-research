-- United Fidelity Bank deposit share, Evansville CBSA. DEPSUMBR. Share in percent.

WITH cbsa_counties AS (
    SELECT column1 AS geo_id_county
    FROM VALUES ('geoId/18163'), ('geoId/18173'), ('geoId/18129'), ('geoId/21101')
),
mkt AS (
    SELECT
        b.fdic_institution_certificate_number AS cert,
        SUM(t.value) AS deposits
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_BRANCH_LOCATIONS_INDEX b
    JOIN cbsa_counties c ON c.geo_id_county = b.geo_id_county
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES t
      ON t.fdic_branch_id = b.fdic_branch_id
     AND t.fdic_institution_id = b.fdic_institution_id
    WHERE t.variable = 'DEPSUMBR'
      AND t.date = (
        SELECT MAX(date)
        FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES
        WHERE variable = 'DEPSUMBR'
    )
    GROUP BY 1
)
SELECT ROUND(100.0 * SUM(IFF(cert = '29566', deposits, 0)) / SUM(deposits), 4) AS share_pct
FROM mkt
