"""
Data-quality checks. Reports issues; does NOT silently drop them.

The staging SQL in /sql handles anomalies defensively. This module is
for the DQ report surfaced in the dashboard and for tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class DQCheck:
    name: str
    value: float
    unit: str          # "count" | "percent"
    status: str        # "PASS" | "WARNING" | "FAIL"
    detail: str = ""


def _status_from_threshold(value: float, warn: float, fail: float) -> str:
    if value >= fail:
        return "FAIL"
    if value >= warn:
        return "WARNING"
    return "PASS"


def check_duplicate_traffic(traffic: pd.DataFrame) -> DQCheck:
    subset = ["session_id", "timestamp", "product_id_viewed"]
    n = int(traffic.duplicated(subset=subset).sum())
    total = max(len(traffic), 1)
    pct = n / total
    return DQCheck(
        "Duplicate traffic rows", n, "count",
        _status_from_threshold(pct, warn=0.005, fail=0.05),
        f"{pct:.2%} of traffic rows",
    )


def check_duplicate_cart(cart: pd.DataFrame) -> DQCheck:
    subset = ["session_id", "timestamp", "action", "product_id"]
    n = int(cart.duplicated(subset=subset).sum())
    total = max(len(cart), 1)
    pct = n / total
    return DQCheck(
        "Duplicate cart rows", n, "count",
        _status_from_threshold(pct, warn=0.005, fail=0.05),
        f"{pct:.2%} of cart rows",
    )


def check_missing_source(traffic: pd.DataFrame) -> DQCheck:
    total = max(len(traffic), 1)
    missing = int(traffic["traffic_source"].isna().sum())
    pct = missing / total
    return DQCheck(
        "Missing traffic source", pct * 100, "percent",
        _status_from_threshold(pct, warn=0.02, fail=0.10),
        f"{missing:,} rows with NULL source",
    )


def check_negative_revenue(orders: pd.DataFrame) -> DQCheck:
    n = int((orders["gross_revenue"] < 0).sum())
    return DQCheck(
        "Negative revenue", n, "count",
        "PASS" if n == 0 else "FAIL",
        "Orders with gross_revenue < 0",
    )


def check_invalid_order_status(orders: pd.DataFrame) -> DQCheck:
    valid = {"paid", "cancelled", "refunded"}
    invalid = orders.loc[~orders["order_status"].isin(valid), "order_status"]
    n = int(len(invalid))
    total = max(len(orders), 1)
    pct = n / total
    return DQCheck(
        "Invalid order status", n, "count",
        _status_from_threshold(pct, warn=0.001, fail=0.01),
        f"Values seen: {sorted(invalid.unique().tolist())[:5]}",
    )


def check_orphan_orders(orders: pd.DataFrame, checkout: pd.DataFrame) -> DQCheck:
    if checkout.empty:
        return DQCheck("Orders without checkout", 0, "count", "PASS", "")
    valid_sessions = set(checkout["session_id"].unique())
    orphans = orders.loc[~orders["session_id"].isin(valid_sessions)]
    n = int(orphans["order_id"].nunique())
    total = max(orders["order_id"].nunique(), 1)
    pct = n / total
    return DQCheck(
        "Orders without checkout", n, "count",
        _status_from_threshold(pct, warn=0.01, fail=0.05),
        f"{pct:.2%} of orders",
    )


def check_orphan_cart(cart: pd.DataFrame, traffic: pd.DataFrame) -> DQCheck:
    valid_sessions = set(traffic["session_id"].unique())
    orphans = cart.loc[~cart["session_id"].isin(valid_sessions)]
    n = int(len(orphans))
    total = max(len(cart), 1)
    pct = n / total
    return DQCheck(
        "Cart events without session", n, "count",
        _status_from_threshold(pct, warn=0.001, fail=0.02),
        f"{pct:.2%} of cart events",
    )


def check_duplicate_order_ids(orders: pd.DataFrame) -> DQCheck:
    dup = orders["order_id"].duplicated().sum()
    n = int(dup)
    total = max(len(orders), 1)
    pct = n / total
    return DQCheck(
        "Duplicate order IDs", n, "count",
        _status_from_threshold(pct, warn=0.001, fail=0.02),
        "Order IDs should be globally unique",
    )


def check_purchase_before_checkout(orders: pd.DataFrame,
                                   checkout: pd.DataFrame) -> DQCheck:
    if orders.empty or checkout.empty:
        return DQCheck("Purchase before checkout", 0, "count", "PASS", "")
    first_checkout = (
        checkout.groupby("session_id")["timestamp"].min().rename("first_checkout")
    )
    first_order = (
        orders.groupby("session_id")["timestamp"].min().rename("first_order")
    )
    merged = pd.concat([first_checkout, first_order], axis=1).dropna()
    invalid = merged[merged["first_order"] < merged["first_checkout"]]
    n = int(len(invalid))
    return DQCheck(
        "Purchase before checkout", n, "count",
        "PASS" if n == 0 else "FAIL",
        "Impossible sequence: order timestamp precedes checkout",
    )


def run_all_checks(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Run every check and return a tidy report DataFrame."""
    traffic = tables["traffic_logs"]
    cart = tables["cart_actions"]
    checkout = tables["checkout_events"]
    orders = tables["orders"]

    checks: list[Callable[..., DQCheck]] = [
        lambda: check_duplicate_traffic(traffic),
        lambda: check_duplicate_cart(cart),
        lambda: check_missing_source(traffic),
        lambda: check_negative_revenue(orders),
        lambda: check_invalid_order_status(orders),
        lambda: check_orphan_orders(orders, checkout),
        lambda: check_orphan_cart(cart, traffic),
        lambda: check_duplicate_order_ids(orders),
        lambda: check_purchase_before_checkout(orders, checkout),
    ]

    rows = []
    for fn in checks:
        try:
            c = fn()
            rows.append({
                "Metric": c.name,
                "Value": c.value,
                "Unit": c.unit,
                "Status": c.status,
                "Detail": c.detail,
            })
        except Exception as e:  # noqa: BLE001
            logger.exception("DQ check failed: %s", e)
            rows.append({
                "Metric": fn.__name__,
                "Value": None, "Unit": "count", "Status": "FAIL",
                "Detail": f"Check error: {e}",
            })

    return pd.DataFrame(rows)