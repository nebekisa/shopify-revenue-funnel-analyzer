-- Core analytical model: one row per session.
-- This is the single source of truth for funnel + revenue metrics.
-- Every downstream metric aggregates from here (never from raw events).
WITH sessions AS (
    SELECT
        session_id,
        user_id,
        MIN(timestamp) AS first_seen_at,
        MAX(timestamp) AS last_seen_at,
        -- First-touch attribution within the session.
        ARBITRARY(traffic_source) AS traffic_source,
        ARBITRARY(device) AS device,
        COUNT(DISTINCT product_id_viewed) AS products_viewed
    FROM stg_traffic
    GROUP BY session_id, user_id
),
cart AS (
    SELECT
        session_id,
        COUNT(DISTINCT CASE WHEN action = 'add_to_cart' THEN product_id END)
            AS products_added,
        COUNT(DISTINCT CASE WHEN action = 'remove_from_cart' THEN product_id END)
            AS products_removed,
        MAX(CASE WHEN action = 'add_to_cart' THEN 1 ELSE 0 END) AS added_to_cart
    FROM stg_cart_actions
    GROUP BY session_id
),
checkout AS (
    SELECT
        session_id,
        MAX(CASE WHEN checkout_status IN ('checkout_started','payment_attempted','payment_failed')
                 THEN 1 ELSE 0 END) AS reached_checkout,
        MAX(CASE WHEN checkout_status = 'payment_attempted' THEN 1 ELSE 0 END)
            AS payment_attempted,
        MAX(CASE WHEN checkout_status = 'payment_failed' THEN 1 ELSE 0 END)
            AS payment_failed,
        MAX(cart_value) AS max_cart_value
    FROM stg_checkout_events
    GROUP BY session_id
),
orders_agg AS (
    SELECT
        session_id,
        MAX(CASE WHEN is_paid = 1 THEN 1 ELSE 0 END) AS purchased,
        SUM(CASE WHEN is_paid = 1 THEN gross_revenue ELSE 0 END) AS gross_revenue,
        SUM(CASE WHEN is_paid = 1 THEN discount_applied ELSE 0 END) AS discount,
        SUM(CASE WHEN is_paid = 1 THEN net_revenue ELSE 0 END) AS net_revenue,
        MAX(order_status) AS order_status
    FROM stg_orders
    GROUP BY session_id
)
SELECT
    s.session_id,
    s.user_id,
    s.first_seen_at,
    s.last_seen_at,
    s.traffic_source,
    s.device,
    s.products_viewed,
    COALESCE(c.added_to_cart, 0)     AS added_to_cart,
    COALESCE(c.products_added, 0)    AS products_added,
    COALESCE(c.products_removed, 0)  AS products_removed,
    COALESCE(co.reached_checkout, 0) AS reached_checkout,
    COALESCE(co.payment_attempted, 0) AS payment_attempted,
    COALESCE(co.payment_failed, 0)   AS payment_failed,
    COALESCE(o.purchased, 0)         AS purchased,
    COALESCE(o.gross_revenue, 0)     AS gross_revenue,
    COALESCE(o.discount, 0)          AS discount,
    COALESCE(o.net_revenue, 0)       AS net_revenue,
    o.order_status
FROM sessions s
LEFT JOIN cart     c  USING (session_id)
LEFT JOIN checkout co USING (session_id)
LEFT JOIN orders_agg o USING (session_id);