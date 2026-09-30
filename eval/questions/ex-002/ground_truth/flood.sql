-- NFIP paid building claims in Renasant's six-state footprint, 2020-2025.
-- Reference for physical/flood-risk exposure, not a score pin.

WITH footprint_states AS (
    SELECT column1 AS state_geo_id
    FROM VALUES
        ('geoId/28'),
        ('geoId/13'),
        ('geoId/01'),
        ('geoId/12'),
        ('geoId/47'),
        ('geoId/22')
)
SELECT
    g.geo_name AS state,
    COUNT(*) AS n_claims,
    ROUND(SUM(c.amount_paid_on_building_claim), 0) AS paid_building_usd
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FEMA_NATIONAL_FLOOD_INSURANCE_PROGRAM_CLAIM_INDEX c
JOIN footprint_states s
  ON s.state_geo_id = c.state_geo_id
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX g
  ON g.geo_id = c.state_geo_id
WHERE c.date_of_loss >= '2020-01-01'
  AND c.date_of_loss < '2026-01-01'
GROUP BY g.geo_name
ORDER BY paid_building_usd DESC
