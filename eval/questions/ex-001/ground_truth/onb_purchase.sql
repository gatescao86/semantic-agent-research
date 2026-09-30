-- Old National Bank home-purchase originations, Evansville four-county CBSA, 2025.
-- HMDA action: loan originated. Amounts in USD.

WITH cbsa_counties AS (
    SELECT column1 AS geo_id_county
    FROM VALUES ('geoId/18163'), ('geoId/18173'), ('geoId/18129'), ('geoId/21101')
)
SELECT ROUND(SUM(IFF(h.loan_purpose = 'Home purchase', h.loan_amount, 0)), 0) AS purchase_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.HOME_MORTGAGE_DISCLOSURE_ATTRIBUTES h
JOIN cbsa_counties c
  ON c.geo_id_county = h.county_geo_id
WHERE h.action_taken = 'Loan originated'
  AND h.year = 2025
  AND h.financial_institution_name = 'Old National Bank'
