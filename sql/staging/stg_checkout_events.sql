-- Validated checkout events.
-- A checkout must be tied to a session that also has traffic (else orphan).
-- We keep every status because checkout behavior is the whole point of
-- this project — dropping failed attempts would erase the leakage signal.
WITH valid_sessions AS (
    SELECT DISTINCT session_id FROM stg_traffic
)
SELECT
    c.checkout_id,
    c.session_id,
    c.user_id,
    CAST(c.timestamp AS TIMESTAMP) AS timestamp,
    c.checkout_status,
    CAST(c.cart_value AS DOUBLE) AS cart_value
FROM checkout_events c
JOIN valid_sessions v USING (session_id)
WHERE c.checkout_status IN ('checkout_started', 'payment_attempted', 'payment_failed');