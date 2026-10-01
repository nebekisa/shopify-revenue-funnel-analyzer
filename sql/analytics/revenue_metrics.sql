-- Revenue metrics from the session model.
-- AOV uses PAID orders only.
WITH paid AS (
    SELECT
        COUNT(*)                     AS paid_order_lines,
        COUNT(DISTINCT session_id)   AS paid_sessions,
        SUM(gross_revenue)           AS gross_revenue,
        SUM(discount)                AS discount,
        SUM(net_revenue)             AS net_revenue
    FROM fct_sessions
    WHERE purchased = 1
),
funnel AS (
    SELECT
        SUM(reached_checkout) AS checkout_sessions,
        SUM(purchased)        AS purchase_sessions
    FROM fct_sessions
)
SELECT
    f.checkout_sessions,
    f.purchase_sessions,
    f.checkout_sessions - f.purchase_sessions AS abandoned_checkout_sessions,
    p.paid_order_lines,
    p.paid_sessions,
    p.gross_revenue,
    p.discount,
    p.net_revenue,
    CASE WHEN p.paid_order_lines > 0
         THEN p.gross_revenue / p.paid_order_lines
         ELSE 0 END                           AS aov,
    -- Estimated revenue opportunity (an ESTIMATE, not lost revenue):
    -- abandoned_checkout_sessions * AOV
    (f.checkout_sessions - f.purchase_sessions)
        * (CASE WHEN p.paid_order_lines > 0
                THEN p.gross_revenue / p.paid_order_lines
                ELSE 0 END)                   AS estimated_abandoned_revenue
FROM funnel f CROSS JOIN paid p;