-- Session-level funnel. Rates are computed on DISTINCT SESSIONS,
-- never on raw events. This is the single most important rule in
-- funnel analytics: raw-event rates get inflated by duplicate
-- tracking, repeated views, and multi-item carts.
WITH base AS (
    SELECT
        COUNT(*)                              AS total_sessions,
        SUM(1)                                AS product_view_sessions,
        SUM(added_to_cart)                    AS add_to_cart_sessions,
        SUM(reached_checkout)                 AS checkout_sessions,
        SUM(purchased)                        AS purchase_sessions
    FROM fct_sessions
)
SELECT
    'Product View' AS stage,
    product_view_sessions AS sessions,
    CAST(NULL AS DOUBLE)  AS conv_from_previous,
    CAST(NULL AS DOUBLE)  AS drop_off,
    1.0 AS cumulative_conversion
FROM base
UNION ALL
SELECT
    'Add to Cart',
    add_to_cart_sessions,
    add_to_cart_sessions * 1.0 / NULLIF(product_view_sessions, 0),
    1 - (add_to_cart_sessions * 1.0 / NULLIF(product_view_sessions, 0)),
    add_to_cart_sessions * 1.0 / NULLIF(product_view_sessions, 0)
FROM base
UNION ALL
SELECT
    'Checkout',
    checkout_sessions,
    checkout_sessions * 1.0 / NULLIF(add_to_cart_sessions, 0),
    1 - (checkout_sessions * 1.0 / NULLIF(add_to_cart_sessions, 0)),
    checkout_sessions * 1.0 / NULLIF(product_view_sessions, 0)
FROM base
UNION ALL
SELECT
    'Purchase',
    purchase_sessions,
    purchase_sessions * 1.0 / NULLIF(checkout_sessions, 0),
    1 - (purchase_sessions * 1.0 / NULLIF(checkout_sessions, 0)),
    purchase_sessions * 1.0 / NULLIF(product_view_sessions, 0)
FROM base;