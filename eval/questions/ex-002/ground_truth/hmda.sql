-- Home-purchase originations in Atlanta and Tupelo, plus Renasant Bank's
-- purchase volume by state in its six-state footprint.
-- HMDA 2025. Action: loan originated. Amounts in USD.
-- Renasant LEI 5493002RF1ERFA2XR050.
-- Atlanta (C12060) has null msa_geo_id in this HMDA extract — join via the
-- CBSA's member counties instead.

WITH footprint_states AS (
    SELECT column1 AS state_geo_id
    FROM VALUES
        ('geoId/28'),
        ('geoId/13'),
        ('geoId/01'),
        ('geoId/12'),
        ('geoId/47'),
        ('geoId/22')
),
cbsa_counties AS (
    SELECT DISTINCT
        r.geo_id AS cbsa_geo_id,
        r.related_geo_id AS county_geo_id
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_RELATIONSHIPS r
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX g
      ON g.geo_id = r.related_geo_id
    WHERE r.geo_id IN ('geoId/C12060', 'geoId/C46180')
      AND g.level = 'County'
),
renasant_by_state AS (
    SELECT
        'renasant_by_state' AS slice,
        g.geo_name,
        h.financial_institution_name,
        COUNT(*) AS n_loans,
        SUM(h.loan_amount) AS purchase_usd
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.HOME_MORTGAGE_DISCLOSURE_ATTRIBUTES h
    JOIN footprint_states s
      ON s.state_geo_id = h.state_geo_id
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX g
      ON g.geo_id = h.state_geo_id
    WHERE h.action_taken = 'Loan originated'
      AND h.year = 2025
      AND h.loan_purpose = 'Home purchase'
      AND h.legal_entity_identifier = '5493002RF1ERFA2XR050'
    GROUP BY g.geo_name, h.financial_institution_name
),
cbsa_purchase AS (
    SELECT
        'cbsa_purchase' AS slice,
        cbsa.geo_name,
        h.financial_institution_name,
        COUNT(*) AS n_loans,
        SUM(h.loan_amount) AS purchase_usd
    FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.HOME_MORTGAGE_DISCLOSURE_ATTRIBUTES h
    JOIN cbsa_counties c
      ON c.county_geo_id = h.county_geo_id
    JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX cbsa
      ON cbsa.geo_id = c.cbsa_geo_id
    WHERE h.action_taken = 'Loan originated'
      AND h.year = 2025
      AND h.loan_purpose = 'Home purchase'
    GROUP BY cbsa.geo_name, h.financial_institution_name
    QUALIFY ROW_NUMBER() OVER (PARTITION BY cbsa.geo_name ORDER BY purchase_usd DESC) <= 8
         OR h.financial_institution_name ILIKE '%Renasant%'
)
SELECT * FROM renasant_by_state
UNION ALL
SELECT * FROM cbsa_purchase
ORDER BY slice, geo_name, purchase_usd DESC
