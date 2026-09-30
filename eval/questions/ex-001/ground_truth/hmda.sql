-- Evansville four-county HMDA originations (same counties as deposits.sql).
-- Action: loan originated. Amounts in USD.

WITH cbsa_counties AS (
    SELECT column1 AS geo_id_county
    FROM VALUES ('geoId/18163'), ('geoId/18173'), ('geoId/18129'), ('geoId/21101')
)
SELECT
    h.year,
    h.financial_institution_name,
    COUNT(*) AS n_loans,
    SUM(IFF(h.loan_purpose = 'Home purchase', h.loan_amount, 0)) AS purchase_usd,
    SUM(h.loan_amount) AS origination_usd,
    ROUND(
        100.0 * SUM(IFF(h.loan_purpose = 'Home purchase', h.loan_amount, 0))
        / NULLIF(SUM(SUM(IFF(h.loan_purpose = 'Home purchase', h.loan_amount, 0))) OVER (PARTITION BY h.year), 0),
        2
    ) AS purchase_share_pct
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.HOME_MORTGAGE_DISCLOSURE_ATTRIBUTES h
JOIN cbsa_counties c
  ON c.geo_id_county = h.county_geo_id
WHERE h.action_taken = 'Loan originated'
  AND h.year IN (2024, 2025)
GROUP BY 1, 2
ORDER BY h.year DESC, purchase_usd DESC
