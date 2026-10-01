-- Cleaned traffic events.
-- Handles: NULL traffic_source, duplicate tracking events.
-- Dedupe rule: identical (session_id, timestamp, product_id_viewed) rows
-- are collapsed to one. This is a tracking double-fire, not user behavior.
WITH ranked AS (
    SELECT
        session_id,
        user_id,
        CAST(timestamp AS TIMESTAMP) AS event_at,
        COALESCE(traffic_source, 'Unknown') AS traffic_source,
        device,
        product_id_viewed,
        ROW_NUMBER() OVER (
            PARTITION BY session_id, timestamp, product_id_viewed
            ORDER BY timestamp
        ) AS rn
    FROM traffic_logs
)
SELECT
    session_id,
    user_id,
    event_at AS timestamp,
    traffic_source,
    device,
    product_id_viewed
FROM ranked
WHERE rn = 1;