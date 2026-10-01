"""Streamlit executive dashboard for the Revenue & Funnel Leakage Analyzer."""
from __future__ import annotations

import traceback
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import config as cfg
from src.analytics import (
    build_filter_clause,
    get_daily_trend,
    get_date_bounds,
    get_funnel_metrics,
    get_revenue_metrics,
    get_segment_performance,
    load_staging_and_marts,
    scenario_relative_checkout_improvement,
)
from src.database import connect, register_raw
from src.data_quality import run_all_checks
from src.utils import money, pct, read_parquet

st.set_page_config(
    page_title="Shopify Revenue & Funnel Leakage Analyzer",
    page_icon="📉",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Cached connection + raw tables
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading data...")
def get_connection():
    """Build (or reuse) a DuckDB connection with raw views + SQL views."""
    con = connect(":memory:")  # in-memory keeps dashboard stateless & fast

    raw = {
        "traffic_logs": read_parquet(cfg.RAW_DIR / "traffic_logs.parquet"),
        "cart_actions": read_parquet(cfg.RAW_DIR / "cart_actions.parquet"),
        "checkout_events": read_parquet(cfg.RAW_DIR / "checkout_events.parquet"),
        "orders": read_parquet(cfg.RAW_DIR / "orders.parquet"),
    }
    register_raw(con, raw)
    load_staging_and_marts(con)
    return con, raw


# ---------------------------------------------------------------------------
# Guarded startup
# ---------------------------------------------------------------------------
try:
    con, raw = get_connection()
    MIN_DATE, MAX_DATE = get_date_bounds(con)
except FileNotFoundError as e:
    st.error(
        "**Raw data not found.**  \n"
        "Run `python generate_data.py` and then `python run_pipeline.py` "
        "before launching the dashboard."
    )
    st.code(str(e))
    st.stop()
except Exception as e:  # noqa: BLE001
    st.error("**Failed to initialize dashboard.**")
    st.code(traceback.format_exc())
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.title("Filters")

date_range = st.sidebar.date_input(
    "Date range",
    value=(MIN_DATE, MAX_DATE),
    min_value=MIN_DATE,
    max_value=MAX_DATE,
)

# date_input returns a tuple of 1 or 2 dates depending on user interaction.
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = MIN_DATE, MAX_DATE

source_options = ["Meta", "Google", "Direct", "Unknown"]
selected_sources = st.sidebar.multiselect(
    "Traffic source", source_options, default=source_options)

device_options = ["mobile", "desktop", "tablet"]
selected_devices = st.sidebar.multiselect(
    "Device", device_options, default=device_options)

if not selected_sources:
    selected_sources = source_options
if not selected_devices:
    selected_devices = device_options

where, params = build_filter_clause(
    start_date=start_date.isoformat(),
    end_date=end_date.isoformat(),
    sources=selected_sources,
    devices=selected_devices,
)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Shopify Revenue & Funnel Leakage Analyzer")
st.caption("Where are we losing customers, and how much revenue is on the table?")


# ---------------------------------------------------------------------------
# Section 1 — Executive KPI ribbon
# ---------------------------------------------------------------------------
try:
    funnel = get_funnel_metrics(con, where, params)
    revenue = get_revenue_metrics(con, where, params)
    scenario = scenario_relative_checkout_improvement(funnel, revenue)
except Exception:  # noqa: BLE001
    st.error("Failed to compute headline metrics.")
    st.code(traceback.format_exc())
    st.stop()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Revenue", money(revenue.gross_revenue))
c2.metric("Paid orders", f"{revenue.paid_order_lines:,}")
c3.metric("Sessions", f"{funnel.product_view_sessions:,}")
c4.metric("Conversion", pct(funnel.overall_conversion))
c5.metric("AOV", money(revenue.aov))
c6.metric("Est. abandoned $", money(revenue.estimated_abandoned_revenue))

st.divider()


# ---------------------------------------------------------------------------
# Section 2 — Revenue trend
# ---------------------------------------------------------------------------
st.subheader("Revenue trend")
try:
    trend = get_daily_trend(con, where, params)
except Exception:  # noqa: BLE001
    trend = pd.DataFrame()

if trend.empty:
    st.info("No data in selected range.")
else:
    metric_choice = st.radio(
        "Metric", ["Revenue", "Orders", "Conversion rate"],
        horizontal=True, label_visibility="collapsed")

    ymap = {
        "Revenue": ("revenue", "Revenue ($)"),
        "Orders": ("orders", "Paid orders"),
        "Conversion rate": ("conversion_rate", "Conversion rate"),
    }
    y_col, y_label = ymap[metric_choice]
    fig = px.line(trend, x="day", y=y_col, markers=True, labels={y_col: y_label})
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 3 — Conversion funnel
# ---------------------------------------------------------------------------
st.subheader("Conversion funnel")

funnel_df = pd.DataFrame({
    "Stage": ["Product View", "Add to Cart", "Checkout", "Purchase"],
    "Sessions": [
        funnel.product_view_sessions,
        funnel.add_to_cart_sessions,
        funnel.checkout_sessions,
        funnel.purchase_sessions,
    ],
})
funnel_df["Conv from prev"] = [
    "—",
    f"{funnel.atc_rate:.1%}",
    f"{funnel.checkout_rate:.1%}",
    f"{funnel.purchase_rate:.1%}",
]
funnel_df["Drop-off"] = [
    "—",
    f"{1 - funnel.atc_rate:.1%}",
    f"{1 - funnel.checkout_rate:.1%}",
    f"{1 - funnel.purchase_rate:.1%}",
]

fig_funnel = go.Figure(go.Funnel(
    y=funnel_df["Stage"],
    x=funnel_df["Sessions"],
    textinfo="value+percent initial",
))
fig_funnel.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig_funnel, use_container_width=True)

st.dataframe(funnel_df, hide_index=True, use_container_width=True)

if funnel.checkout_drop_off > cfg.CHECKOUT_LEAKAGE_ALERT_THRESHOLD:
    st.error(
        f"Critical checkout leakage: "
        f"{funnel.checkout_drop_off:.1%} of checkout sessions do not convert."
    )


# ---------------------------------------------------------------------------
# Section 4 — Financial opportunity
# ---------------------------------------------------------------------------
st.subheader("Financial opportunity")

col_a, col_b = st.columns(2)
with col_a:
    st.metric("Estimated Revenue Opportunity",
              money(revenue.estimated_abandoned_revenue))
    st.caption(
        "We estimate this opportunity by applying the observed AOV to "
        "checkout sessions that did not result in a successful purchase. "
        "This is a scenario estimate, not guaranteed recoverable revenue."
    )
with col_b:
    st.metric(
        "5% relative checkout improvement",
        money(scenario["incremental_revenue"]),
        delta=f"+{scenario['additional_purchases']:.0f} purchases",
    )
    st.caption(
        f"Checkout→purchase rate would move from "
        f"{pct(scenario['current_rate'])} to {pct(scenario['new_rate'])}. "
        "This is a scenario, not a forecast."
    )


# ---------------------------------------------------------------------------
# Section 5 — Segment performance
# ---------------------------------------------------------------------------
st.subheader("Segment performance")

seg_dim = st.radio("View by", ["Traffic source", "Device"],
                   horizontal=True, label_visibility="collapsed")
dim_col = "traffic_source" if seg_dim == "Traffic source" else "device"

try:
    seg = get_segment_performance(con, dim_col, where, params)
except Exception:  # noqa: BLE001
    seg = pd.DataFrame()

if seg.empty:
    st.info("No segment data in selected range.")
else:
    seg_display = seg.copy()
    for c in ["atc_rate", "checkout_rate", "purchase_rate", "conversion_rate"]:
        seg_display[c] = seg_display[c].map(lambda v: pct(v) if pd.notna(v) else "—")
    seg_display["revenue"] = seg_display["revenue"].map(money)
    seg_display["aov"] = seg_display["aov"].map(money)
    seg_display = seg_display.rename(columns={
        "segment": seg_dim.replace("_", " ").title(),
        "sessions": "Sessions",
        "orders": "Orders",
        "revenue": "Revenue",
        "atc_rate": "ATC rate",
        "checkout_rate": "Checkout rate",
        "purchase_rate": "Purchase rate",
        "conversion_rate": "Conversion",
        "aov": "AOV",
    })
    st.dataframe(seg_display, hide_index=True, use_container_width=True)

    if len(seg) >= 2 and dim_col == "device":
        mobile = seg.loc[seg["segment"] == "mobile"]
        desktop = seg.loc[seg["segment"] == "desktop"]
        if not mobile.empty and not desktop.empty:
            m_cr = mobile.iloc[0]["purchase_rate"]
            d_cr = desktop.iloc[0]["purchase_rate"]
            st.info(
                f"Mobile checkout→purchase rate is {pct(m_cr)}, "
                f"compared with {pct(d_cr)} on desktop."
            )


# ---------------------------------------------------------------------------
# Section 6 — Data quality panel
# ---------------------------------------------------------------------------
with st.expander("Data Quality & Reliability", expanded=False):
    try:
        dq = run_all_checks(raw)
        st.caption(
            "Analytics conclusions depend on tracking quality. "
            "These checks report — but do not silently delete — anomalies."
        )
        st.dataframe(dq, hide_index=True, use_container_width=True)
    except Exception:  # noqa: BLE001
        st.error("Failed to run data-quality checks.")
        st.code(traceback.format_exc())


st.divider()
st.caption(
    "Synthetic data. Abandoned-revenue figures are estimates. "
    "Checkout improvement is a scenario, not a forecast."
)