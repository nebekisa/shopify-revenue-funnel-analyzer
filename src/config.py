"""Central configuration. All magic numbers live here."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# ---------- Paths ----------
ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
DATA_DIR: Final[Path] = ROOT_DIR / "data"
RAW_DIR: Final[Path] = DATA_DIR / "raw"
PROCESSED_DIR: Final[Path] = DATA_DIR / "processed"
SQL_DIR: Final[Path] = ROOT_DIR / "sql"

# ---------- Reproducibility ----------
RANDOM_SEED: Final[int] = 42

# ---------- Simulation window ----------
SIMULATION_DAYS: Final[int] = 30
# Anchor to a fixed date so tests are deterministic across runs.
SIMULATION_START: Final[str] = "2024-01-01"

# ---------- Traffic volume ----------
# Base daily sessions; weekend uplift applied inside generator.
BASE_DAILY_SESSIONS: Final[int] = 900
WEEKEND_MULTIPLIER: Final[float] = 1.35

# ---------- Funnel probabilities (these SHAPE behavior, they do not force outputs) ----------
P_VIEW_MULTIPLE_PRODUCTS: Final[float] = 0.55       # of viewers, view >1 product
P_ADD_TO_CART_GIVEN_VIEW: Final[float] = 0.18       # baseline; modulated per-segment
P_REMOVE_FROM_CART: Final[float] = 0.12             # of cart sessions
P_CHECKOUT_GIVEN_CART: Final[float] = 0.55          # baseline; modulated per-segment
P_PAYMENT_ATTEMPTED_GIVEN_CHECKOUT: Final[float] = 0.82
P_PURCHASE_GIVEN_PAYMENT_ATTEMPTED: Final[float] = 0.62

# ---------- Segment multipliers (realistic heterogeneity) ----------
DEVICE_MULTIPLIERS: Final[dict[str, dict[str, float]]] = {
    "mobile":  {"atc": 0.85, "checkout": 0.80, "purchase": 0.85},
    "desktop": {"atc": 1.20, "checkout": 1.15, "purchase": 1.10},
    "tablet":  {"atc": 0.95, "checkout": 0.95, "purchase": 0.98},
}

SOURCE_MULTIPLIERS: Final[dict[str, dict[str, float]]] = {
    "Meta":   {"atc": 0.90, "checkout": 0.95, "purchase": 0.90},
    "Google": {"atc": 1.10, "checkout": 1.05, "purchase": 1.08},
    "Direct": {"atc": 1.15, "checkout": 1.10, "purchase": 1.12},
}

DEVICES: Final[list[str]] = ["mobile", "desktop", "tablet"]
DEVICE_WEIGHTS: Final[list[float]] = [0.62, 0.33, 0.05]

TRAFFIC_SOURCES: Final[list[str]] = ["Meta", "Google", "Direct"]
SOURCE_WEIGHTS: Final[list[float]] = [0.42, 0.38, 0.20]

# ---------- Order economics ----------
# Log-normal for realistic right-skewed order values.
ORDER_VALUE_MEAN_LOG: Final[float] = 3.9      # ~ $50 median
ORDER_VALUE_SIGMA_LOG: Final[float] = 0.55
DISCOUNT_PROBABILITY: Final[float] = 0.28
DISCOUNT_RANGE: Final[tuple[float, float]] = (0.05, 0.35)
ORDER_STATUS_WEIGHTS: Final[dict[str, float]] = {
    "paid": 0.92,
    "cancelled": 0.05,
    "refunded": 0.03,
}

# ---------- Product catalog ----------
N_PRODUCTS: Final[int] = 40
PRODUCT_ID_PREFIX: Final[str] = "SKU"

# ---------- Data quality — deliberate imperfections ----------
DQ_MISSING_SOURCE_RATE: Final[float] = 0.038       # 3.8% missing traffic_source
DQ_DUPLICATE_TRAFFIC_RATE: Final[float] = 0.012    # 1.2% duplicate traffic rows
DQ_DUPLICATE_CART_RATE: Final[float] = 0.018       # 1.8% duplicate cart rows
DQ_INVALID_ORDER_STATUS_RATE: Final[float] = 0.004 # 0.4% invalid statuses
DQ_ORPHAN_ORDER_RATE: Final[float] = 0.021         # 2.1% orders without checkout

# ---------- Business thresholds for dashboard alerts ----------
CHECKOUT_LEAKAGE_ALERT_THRESHOLD: Final[float] = 0.70   # 70% drop-off = warn

# ---------- Output database ----------
DUCKDB_PATH: Final[Path] = PROCESSED_DIR / "analytics.duckdb"

@dataclass(frozen=True)
class FunnelStage:
    name: str
    key: str

FUNNEL_STAGES: Final[tuple[FunnelStage, ...]] = (
    FunnelStage("Product View", "product_view_sessions"),
    FunnelStage("Add to Cart", "add_to_cart_sessions"),
    FunnelStage("Checkout", "checkout_sessions"),
    FunnelStage("Purchase", "purchase_sessions"),
)