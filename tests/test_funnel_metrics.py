"""Tests that enforce the fundamental monotonicity of the funnel."""
from __future__ import annotations

import pytest

from src import config as cfg
from src.analytics import get_funnel_metrics, load_staging_and_marts
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


def test_funnel_is_monotonic(con):
    f = get_funnel_metrics(con)
    assert f.purchase_sessions <= f.checkout_sessions
    assert f.checkout_sessions <= f.add_to_cart_sessions
    assert f.add_to_cart_sessions <= f.product_view_sessions


def test_rates_within_unit_interval(con):
    f = get_funnel_metrics(con)
    assert 0.0 <= f.atc_rate <= 1.0
    assert 0.0 <= f.checkout_rate <= 1.0
    assert 0.0 <= f.purchase_rate <= 1.0
    assert 0.0 <= f.overall_conversion <= 1.0


def test_conversion_rates_are_plausible(con):
    """Simulation should land within the ranges described in the spec."""
    f = get_funnel_metrics(con)
    assert 0.05 <= f.atc_rate <= 0.35, f"ATC rate out of range: {f.atc_rate}"
    assert 0.20 <= f.checkout_rate <= 0.80, f"Checkout rate out of range: {f.checkout_rate}"
    assert 0.005 <= f.overall_conversion <= 0.08, \
        f"Overall conversion out of range: {f.overall_conversion}"