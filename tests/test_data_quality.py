"""Tests for data-quality detection logic."""
from __future__ import annotations

import pandas as pd

from src.data_quality import (
    check_duplicate_cart, check_duplicate_order_ids,
    check_invalid_order_status, check_missing_source,
    check_negative_revenue,
)


def test_duplicate_detection_works():
    df = pd.DataFrame({
        "session_id": ["s1", "s1", "s2"],
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"]),
        "action": ["add_to_cart", "add_to_cart", "add_to_cart"],
        "product_id": ["p1", "p1", "p2"],
    })
    check = check_duplicate_cart(df)
    assert check.value == 1


def test_missing_source_detection():
    df = pd.DataFrame({
        "traffic_source": ["Meta", None, None, "Google"],
    })
    check = check_missing_source(df)
    assert abs(check.value - 50.0) < 0.001


def test_negative_revenue_detection():
    df = pd.DataFrame({"gross_revenue": [10.0, -5.0, 3.0]})
    check = check_negative_revenue(df)
    assert check.value == 1
    assert check.status == "FAIL"


def test_invalid_order_status_detection():
    df = pd.DataFrame({"order_status": ["paid", "unknwon", "refunded"]})
    check = check_invalid_order_status(df)
    assert check.value == 1


def test_duplicate_order_ids():
    df = pd.DataFrame({"order_id": ["o1", "o1", "o2"]})
    check = check_duplicate_order_ids(df)
    assert check.value == 1