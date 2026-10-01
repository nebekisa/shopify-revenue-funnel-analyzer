"""Analytics layer: loads SQL models, exposes typed metric functions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import duckdb
import pandas as pd

from src import config as cfg
from src.database import query
from src.utils import get_logger, safe_div

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Load / refresh
# ---------------------------------------------------------------------------

def load_staging_and_marts(con: duckdb.DuckDBPyConnection) -> None:
    """Register raw views, then run staging + mart SQL files in order."""
    order = [
        cfg.SQL_DIR / "staging" / "stg_traffic.sql",
        cfg.SQL_DIR / "staging" / "stg_cart_actions.sql",
        cfg.SQL_DIR / "staging" / "stg_checkout_events.sql",
        cfg.SQL_DIR / "staging" / "stg_orders.sql",
    ]
    for p in order:
        sql = p.read_text(encoding="utf-8").rstrip().rstrip(";")
        con.execute(f"CREATE OR REPLACE VIEW {p.stem} AS {sql}")

    mart = cfg.SQL_DIR / "marts" / "fct_sessions.sql"
    sql = mart.read_text(encoding="utf-8").rstrip().rstrip(";")
    con.execute(f"CREATE OR REPLACE VIEW fct_sessions AS {sql}")
    logger.info("Views built: stg_* + fct_sessions")


# ---------------------------------------------------------------------------
# Typed metrics
# ---------------------------------------------------------------------------

@dataclass
class FunnelMetrics:
    product_view_sessions: int
    add_to_cart_sessions: int
    checkout_sessions: int
    purchase_sessions: int

    @property
    def atc_rate(self) -> float:
        return safe_div(self.add_to_cart_sessions, self.product_view_sessions)

    @property
    def checkout_rate(self) -> float:
        return safe_div(self.checkout_sessions, self.add_to_cart_sessions)

    @property
    def purchase_rate(self) -> float:
        return safe_div(self.purchase_sessions, self.checkout_sessions)

    @property
    def overall_conversion(self) -> float:
        return safe_div(self.purchase_sessions, self.product_view_sessions)

    @property
    def checkout_drop_off(self) -> float:
        return 1.0 - self.purchase_rate

    @property
    def abandoned_checkout_sessions(self) -> int:
        return max(self.checkout_sessions - self.purchase_sessions, 0)


@dataclass
class RevenueMetrics:
    gross_revenue: float
    discount: float
    net_revenue: float
    aov: float
    paid_order_lines: int
    estimated_abandoned_revenue: float


# ---------------------------------------------------------------------------
# Filter builder — SAFE, uses literal parameters, no $ binding surprises
# ---------------------------------------------------------------------------

def build_filter_clause(
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    sources: Iterable[str] | None = None,
    devices: Iterable[str] | None = None,
) -> tuple[str, dict]:
    """
    Return (WHERE clause, params dict).

    We intentionally use DuckDB's named parameter syntax ($name) for
    scalars only. For list membership we expand placeholders manually
    (safely — values come from a whitelist controlled by the app).
    """
    clauses: list[str] = []
    params: dict = {}

    if start_date is not None:
        clauses.append("first_seen_at >= $start_date::TIMESTAMP")
        params["start_date"] = str(start_date)

    if end_date is not None:
        # Inclusive end: end of day.
        clauses.append("first_seen_at < ($end_date::TIMESTAMP + INTERVAL 1 DAY)")
        params["end_date"] = str(end_date)

    if sources:
        sources = [s for s in sources if s]
        if sources:
            placeholders = ", ".join(f"$src_{i}" for i in range(len(sources)))
            clauses.append(f"traffic_source IN ({placeholders})")
            for i, s in enumerate(sources):
                params[f"src_{i}"] = s

    if devices:
        devices = [d for d in devices if d]
        if devices:
            placeholders = ", ".join(f"$dev_{i}" for i in range(len(devices)))
            clauses.append(f"device IN ({placeholders})")
            for i, d in enumerate(devices):
                params[f"dev_{i}"] = d

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


# ---------------------------------------------------------------------------
# Metric queries
# ---------------------------------------------------------------------------

def get_funnel_metrics(con: duckdb.DuckDBPyConnection,
                       where: str = "", params: dict | None = None) -> FunnelMetrics:
    sql = f"""
        SELECT
            COUNT(*)               AS product_view_sessions,
            SUM(added_to_cart)     AS add_to_cart_sessions,
            SUM(reached_checkout)  AS checkout_sessions,
            SUM(purchased)         AS purchase_sessions
        FROM fct_sessions
        {where}
    """
    df = query(con, sql, params)
    row = df.iloc[0]
    return FunnelMetrics(
        product_view_sessions=int(row["product_view_sessions"] or 0),
        add_to_cart_sessions=int(row["add_to_cart_sessions"] or 0),
        checkout_sessions=int(row["checkout_sessions"] or 0),
        purchase_sessions=int(row["purchase_sessions"] or 0),
    )


def get_revenue_metrics(con: duckdb.DuckDBPyConnection,
                        where: str = "", params: dict | None = None) -> RevenueMetrics:
    # NOTE: `where` is applied to BOTH CTEs — DuckDB allows reusing named
    # params within a single statement.
    paid_where = f"{where} {'AND' if where else 'WHERE'} purchased = 1"
    sql = f"""
        WITH paid AS (
            SELECT
                COUNT(*)           AS paid_order_lines,
                SUM(gross_revenue) AS gross_revenue,
                SUM(discount)      AS discount,
                SUM(net_revenue)   AS net_revenue
            FROM fct_sessions
            {paid_where}
        ),
        funnel AS (
            SELECT SUM(reached_checkout) AS checkout_sessions,
                   SUM(purchased)        AS purchase_sessions
            FROM fct_sessions
            {where}
        )
        SELECT
            p.gross_revenue, p.discount, p.net_revenue, p.paid_order_lines,
            CASE WHEN p.paid_order_lines > 0
                 THEN p.gross_revenue / p.paid_order_lines ELSE 0 END AS aov,
            (f.checkout_sessions - f.purchase_sessions)
              * (CASE WHEN p.paid_order_lines > 0
                      THEN p.gross_revenue / p.paid_order_lines
                      ELSE 0 END) AS estimated_abandoned_revenue
        FROM paid p CROSS JOIN funnel f
    """
    df = query(con, sql, params)
    row = df.iloc[0]
    return RevenueMetrics(
        gross_revenue=float(row["gross_revenue"] or 0),
        discount=float(row["discount"] or 0),
        net_revenue=float(row["net_revenue"] or 0),
        aov=float(row["aov"] or 0),
        paid_order_lines=int(row["paid_order_lines"] or 0),
        estimated_abandoned_revenue=float(row["estimated_abandoned_revenue"] or 0),
    )


def get_daily_trend(con: duckdb.DuckDBPyConnection,
                    where: str = "", params: dict | None = None) -> pd.DataFrame:
    sql = f"""
        SELECT
            DATE_TRUNC('day', first_seen_at) AS day,
            COUNT(*)                          AS sessions,
            SUM(purchased)                    AS orders,
            SUM(gross_revenue)                AS revenue,
            SUM(purchased) * 1.0 / NULLIF(COUNT(*), 0) AS conversion_rate
        FROM fct_sessions
        {where}
        GROUP BY 1
        ORDER BY 1
    """
    return query(con, sql, params)


def get_segment_performance(con: duckdb.DuckDBPyConnection,
                            dimension: str,
                            where: str = "", params: dict | None = None) -> pd.DataFrame:
    if dimension not in {"traffic_source", "device"}:
        raise ValueError(f"Unsupported dimension: {dimension}")

    sql = f"""
        SELECT
            {dimension} AS segment,
            COUNT(*)                                   AS sessions,
            SUM(purchased)                             AS orders,
            SUM(gross_revenue)                         AS revenue,
            SUM(added_to_cart) * 1.0 / NULLIF(COUNT(*), 0) AS atc_rate,
            SUM(reached_checkout) * 1.0 / NULLIF(SUM(added_to_cart), 0) AS checkout_rate,
            SUM(purchased) * 1.0 / NULLIF(SUM(reached_checkout), 0)      AS purchase_rate,
            SUM(purchased) * 1.0 / NULLIF(COUNT(*), 0)                   AS conversion_rate,
            CASE WHEN SUM(purchased) > 0
                 THEN SUM(gross_revenue) / SUM(purchased) ELSE 0 END     AS aov
        FROM fct_sessions
        {where}
        GROUP BY 1
        ORDER BY sessions DESC
    """
    return query(con, sql, params)


def scenario_relative_checkout_improvement(
    funnel: FunnelMetrics,
    revenue: RevenueMetrics,
    relative_improvement: float = 0.05,
) -> dict:
    current_rate = funnel.purchase_rate
    new_rate = min(current_rate * (1 + relative_improvement), 1.0)
    additional_purchases = funnel.checkout_sessions * (new_rate - current_rate)
    incremental_revenue = additional_purchases * revenue.aov
    return {
        "current_rate": current_rate,
        "new_rate": new_rate,
        "additional_purchases": additional_purchases,
        "incremental_revenue": incremental_revenue,
    }


def get_date_bounds(con: duckdb.DuckDBPyConnection) -> tuple[date, date]:
    """Return (min_date, max_date) as Python dates for the sidebar."""
    df = con.execute(
        "SELECT MIN(first_seen_at) AS mn, MAX(first_seen_at) AS mx FROM fct_sessions"
    ).df()
    mn = pd.to_datetime(df.iloc[0]["mn"]).date()
    mx = pd.to_datetime(df.iloc[0]["mx"]).date()
    return mn, mx