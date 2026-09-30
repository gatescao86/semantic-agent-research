-- Liberty Credit Union HMDA originations, Evansville CBSA, 2025.
-- Action: loan originated. Amounts in USD. MSA grain matches 001 / SOD CBSA.

SELECT ROUND(SUM(h.loan_amount), 0) AS origination_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.HOME_MORTGAGE_DISCLOSURE_ATTRIBUTES h
WHERE h.msa_geo_id = 'geoId/C21780'
  AND h.year = 2025
  AND h.action_taken = 'Loan originated'
  AND h.financial_institution_name = 'Liberty Credit Union'
