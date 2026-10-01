"""Tests for revenue semantics."""
from __future__ import annotations

import pytest

from src import config as cfg
from src.analytics import (
    get_funnel_metrics, get_revenue_metrics, load_staging_and_marts,
    scenario_relative_checkout_improvement,
)
from src.database import connect, register_raw
from src.utils import read_parquet


@pytest.fixture(scope="module")
def con():
    raw = {
        "traffic_logs": read_parquet(cfg.RAW_DIR / "traffic_logs.parquet"),
        "cart_actions": read_parquet(cfg.RAW_DIR / "cart_actions.parquet"),
        "checkout_events": read_parquet(cfg.RAW_DIR / "checkout_events.parquet"),
        "orders": read_parquet(cfg.RAW_DIR / "orders.parquet"),
    }
    connection = connect(":memory:")
    register_raw(connection, raw)
    load_staging_and_marts(connection)
    yield connection
    connection.close()


def test_revenue_non_negative(con):
    r = get_revenue_metrics(con)
    assert r.gross_revenue >= 0
    assert r.net_revenue >= 0
    assert r.discount >= 0


def test_aov_calculation(con):
    r = get_revenue_metrics(con)
    if r.paid_order_lines > 0:
        expected = r.gross_revenue / r.paid_order_lines
        assert abs(r.aov - expected) < 0.01


def test_estimated_abandoned_revenue_formula(con):
    f = get_funnel_metrics(con)
    r = get_revenue_metrics(con)
    expected = (f.checkout_sessions - f.purchase_sessions) * r.aov
    assert abs(r.estimated_abandoned_revenue - expected) < 1.0


def test_scenario_math(con):
    f = get_funnel_metrics(con)
    r = get_revenue_metrics(con)
    s = scenario_relative_checkout_improvement(f, r, 0.05)
    assert s["new_rate"] == pytest.approx(s["current_rate"] * 1.05, rel=1e-6)
    expected_add = f.checkout_sessions * (s["new_rate"] - s["current_rate"])
    assert s["additional_purchases"] == pytest.approx(expected_add, rel=1e-6)
    assert s["incremental_revenue"] == pytest.approx(expected_add * r.aov, rel=1e-6)