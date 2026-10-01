-- Funnel + revenue by traffic source, device, and day.
-- Rate columns are session-based.
WITH daily AS (
    SELECT
        DATE_TRUNC('day', first_seen_at) AS day,
        COUNT(*)                          AS sessions,
        SUM(purchased)                    AS orders,
        SUM(gross_revenue)                AS revenue,
        AVG(CASE WHEN purchased = 1 THEN gross_revenue END) AS aov,
        SUM(added_to_cart) * 1.0 / COUNT(*) AS atc_rate,
        SUM(reached_checkout) * 1.0 / NULLIF(SUM(added_to_cart), 0) AS checkout_rate,
        SUM(purchased) * 1.0 / NULLIF(SUM(reached_checkout), 0)      AS purchase_rate,
        SUM(purchased) * 1.0 / COUNT(*)                              AS conversion_rate
    FROM fct_sessions
    GROUP BY 1
)
SELECT * FROM daily ORDER BY day;

-- Separately, the by-source and by-device rollups live in
-- their own queries in analytics.py to keep each visualization
-- independent and filterable.