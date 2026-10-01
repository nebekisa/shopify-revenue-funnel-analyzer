-- Validated orders.
-- Rules:
--   * Invalid statuses ('unknwon' etc.) -> excluded from revenue, retained as data quality signal.
--   * Negative revenue -> excluded (should never occur).
--   * Only 'paid' orders contribute to revenue.
WITH cleaned AS (
    SELECT
        order_id,
        session_id,
        user_id,
        CAST(timestamp AS TIMESTAMP) AS timestamp,
        CAST(gross_revenue AS DOUBLE) AS gross_revenue,
        CAST(discount_applied AS DOUBLE) AS discount_applied,
        product_id,
        order_status
    FROM orders
    WHERE order_status IN ('paid', 'cancelled', 'refunded')
      AND gross_revenue >= 0
)
SELECT
    order_id,
    session_id,
    user_id,
    timestamp,
    gross_revenue,
    discount_applied,
    product_id,
    order_status,
    -- Net revenue: what the business actually keeps.
    (gross_revenue - discount_applied) AS net_revenue,
    CASE WHEN order_status = 'paid' THEN 1 ELSE 0 END AS is_paid
FROM cleaned;