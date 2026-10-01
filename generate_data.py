"""CLI entry point: generate synthetic raw data -> parquet."""
from __future__ import annotations

import sys

from src import config as cfg
from src.data_generation import generate_raw_events, validation_report
from src.utils import ensure_dirs, get_logger, write_parquet

logger = get_logger("generate_data")


def main() -> int:
    ensure_dirs(cfg.RAW_DIR, cfg.PROCESSED_DIR)
    logger.info("Generating %d days of synthetic Shopify event data...",
                cfg.SIMULATION_DAYS)

    tables = generate_raw_events()

    for name, df in tables.items():
        out = cfg.RAW_DIR / f"{name}.parquet"
        write_parquet(df, out)
        logger.info("Wrote %-18s -> %s (%d rows)", name, out.name, len(df))

    report = validation_report(tables)
    logger.info("Funnel validation report:\n%s", report.to_string(index=False))

    # Save report for the README / tests to reference.
    report.to_csv(cfg.PROCESSED_DIR / "funnel_validation.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())