"""CLI entry point: load raw parquet -> build SQL views -> persist DQ report."""
from __future__ import annotations

import sys

import pandas as pd

from src import config as cfg
from src.analytics import (
    get_funnel_metrics, get_revenue_metrics, load_staging_and_marts,
    scenario_relative_checkout_improvement,
)
from src.data_quality import run_all_checks
from src.database import connect, register_raw
from src.utils import ensure_dirs, get_logger, read_parquet, pct, money

logger = get_logger("run_pipeline")


def main() -> int:
    ensure_dirs(cfg.PROCESSED_DIR)

    # 1. Load raw tables
    raw = {
        "traffic_logs": read_parquet(cfg.RAW_DIR / "traffic_logs.parquet"),
        "cart_actions": read_parquet(cfg.RAW_DIR / "cart_actions.parquet"),
        "checkout_events": read_parquet(cfg.RAW_DIR / "checkout_events.parquet"),
        "orders": read_parquet(cfg.RAW_DIR / "orders.parquet"),
    }

    # 2. Data quality report
    dq = run_all_checks(raw)
    dq.to_csv(cfg.PROCESSED_DIR / "data_quality_report.csv", index=False)
    logger.info("Data quality report:\n%s", dq.to_string(index=False))

    # 3. Build DuckDB views
    con = connect()
    register_raw(con, raw)
    load_staging_and_marts(con)

    # 4. Compute headline metrics + scenario
    funnel = get_funnel_metrics(con)
    revenue = get_revenue_metrics(con)
    scenario = scenario_relative_checkout_improvement(funnel, revenue)

    logger.info("=" * 60)
    logger.info("FUNNEL (session-level)")
    logger.info("  Product-view sessions : %s", f"{funnel.product_view_sessions:,}")
    logger.info("  Add-to-cart sessions  : %s  (%s)",
                f"{funnel.add_to_cart_sessions:,}", pct(funnel.atc_rate))
    logger.info("  Checkout sessions     : %s  (%s)",
                f"{funnel.checkout_sessions:,}", pct(funnel.checkout_rate))
    logger.info("  Purchase sessions     : %s  (%s)",
                f"{funnel.purchase_sessions:,}", pct(funnel.purchase_rate))
    logger.info("  Overall conversion    : %s", pct(funnel.overall_conversion))
    logger.info("  Checkout drop-off     : %s", pct(funnel.checkout_drop_off))
    logger.info("-" * 60)
    logger.info("REVENUE")
    logger.info("  Gross revenue         : %s", money(revenue.gross_revenue))
    logger.info("  Net revenue           : %s", money(revenue.net_revenue))
    logger.info("  AOV                   : %s", money(revenue.aov))
    logger.info("  Estimated abandoned $ : %s",
                money(revenue.estimated_abandoned_revenue))
    logger.info("-" * 60)
    logger.info("SCENARIO: 5%% relative improvement in checkout->purchase")
    logger.info("  Current rate          : %s", pct(scenario["current_rate"]))
    logger.info("  Target rate           : %s", pct(scenario["new_rate"]))
    logger.info("  Additional purchases  : %.0f", scenario["additional_purchases"])
    logger.info("  Incremental revenue   : %s", money(scenario["incremental_revenue"]))
    logger.info("=" * 60)

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())