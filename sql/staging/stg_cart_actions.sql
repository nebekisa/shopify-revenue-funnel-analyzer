-- Deduplicated cart events.
-- A user genuinely can add the same product twice at different times,
-- so we dedupe on (session_id, timestamp, action, product_id) only.
WITH ranked AS (
    SELECT
        session_id,
        user_id,
        CAST(timestamp AS TIMESTAMP) AS event_at,
        action,
        product_id,
        ROW_NUMBER() OVER (
            PARTITION BY session_id, timestamp, action, product_id
            ORDER BY timestamp
        ) AS rn
    FROM cart_actions
    WHERE action IN ('add_to_cart', 'remove_from_cart')
)
SELECT
    session_id,
    user_id,
    event_at AS timestamp,
    action,
    product_id
FROM ranked
WHERE rn = 1;