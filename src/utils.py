"""Shared helpers: logging, IO, formatting."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd


def get_logger(name: str) -> logging.Logger:
    """Consistent logger with a sane default format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Persist a DataFrame as parquet. Used for the 'processed' layer."""
    ensure_dirs(path.parent)
    df.to_parquet(path, index=False)


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def pct(x: float, decimals: int = 2) -> str:
    """Format a fraction as a percent string."""
    return f"{x * 100:.{decimals}f}%"


def money(x: float, decimals: int = 2) -> str:
    return f"${x:,.{decimals}f}"


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide with a sensible default — prevents ZeroDivisionError in metrics."""
    if denominator is None or denominator == 0:
        return default
    return numerator / denominator


def as_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.to_dict(orient="records")