from __future__ import annotations

"""SQLite setup, CSV ingestion, and data-quality handling.

Schema
------
The ``sales`` table stores one row per transaction line from the supplied CSV.
Columns mirror the CSV with normalised types and an extra ``data_quality_note``
column that records validation problems without discarding the row.

Revenue definition
------------------
Net revenue = quantity × unit_price − discount_amount
Only rows satisfying the ``revenue_filter()`` predicate are included:
  - status is 'completed' (case-insensitive)
  - quantity > 0
  - unit_price IS NOT NULL AND unit_price > 0
  - discount_amount >= 0 AND discount_amount <= quantity * unit_price
Returned transactions and rows with invalid numerics are excluded.
"""

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "sales.db"))
CSV_PATH = Path(os.getenv("SALES_CSV_PATH", BASE_DIR / "data" / "sales_data.csv"))

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """\
CREATE TABLE IF NOT EXISTS sales (
    transaction_id    TEXT PRIMARY KEY,
    order_date        TEXT NOT NULL,
    product           TEXT NOT NULL,
    category          TEXT NOT NULL,
    region            TEXT NOT NULL,
    sales_channel     TEXT NOT NULL,
    quantity          INTEGER NOT NULL,
    unit_price        REAL,
    discount_amount   REAL NOT NULL DEFAULT 0,
    status            TEXT NOT NULL,
    data_quality_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_sales_date    ON sales(order_date);
CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product);
CREATE INDEX IF NOT EXISTS idx_sales_region  ON sales(region);
CREATE INDEX IF NOT EXISTS idx_sales_category ON sales(category);
CREATE INDEX IF NOT EXISTS idx_sales_status  ON sales(status);
"""

# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a connection with row-factory enabled."""
    path = db_path or DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ---------------------------------------------------------------------------
# CSV ingestion
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "Transaction_Id", "Order_date", "Product", "Category", "Region",
    "Sales_channel", "Quantity", "Unit_price", "Discount_amount", "Status",
]


def initialize_database(csv_path: str | Path | None = None) -> dict:
    """Create the table and load the CSV.  Idempotent – safe to call on every startup.

    Policy for problematic rows
    ---------------------------
    * Rows missing identity, date, or descriptive fields are **dropped** (they
      cannot be meaningfully stored).
    * Duplicate ``Transaction_Id`` values keep the first occurrence.
    * Rows with missing/invalid numeric values are **kept** in the database
      but annotated in ``data_quality_note`` and excluded from revenue queries
      by the ``revenue_filter()`` predicate.
    * The supplied CSV is **not modified**.

    Returns a summary dict with ingestion statistics.
    """
    source = Path(csv_path) if csv_path else CSV_PATH
    if not source.exists():
        raise FileNotFoundError(f"Sales CSV not found: {source}")

    df = pd.read_csv(source)
    original_row_count = len(df)

    # --- Column validation ---
    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")

    df = df[REQUIRED_COLUMNS].copy()

    # --- Type coercion ---
    df["Order_date"] = pd.to_datetime(df["Order_date"], format="%d-%m-%Y", errors="coerce")
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["Unit_price"] = pd.to_numeric(df["Unit_price"], errors="coerce")
    df["Discount_amount"] = pd.to_numeric(df["Discount_amount"], errors="coerce")

    for col in ["Transaction_Id", "Product", "Category", "Region", "Sales_channel", "Status"]:
        df[col] = df[col].astype("string").str.strip()

    # --- Drop rows that cannot be identified ---
    mandatory = ["Transaction_Id", "Product", "Category", "Region", "Sales_channel", "Status"]
    before_mandatory = len(df)
    df = df.dropna(subset=mandatory + ["Order_date"])
    dropped_mandatory = before_mandatory - len(df)

    # --- Deduplicate ---
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["Transaction_Id"], keep="first")
    duplicates_removed = before_dedup - len(df)

    # --- Data-quality annotation (row-level) ---
    notes = []
    for row in df.itertuples(index=False):
        problems = []
        if pd.isna(row.Quantity) or row.Quantity < 0:
            problems.append("missing/negative quantity")
        elif row.Quantity == 0:
            problems.append("zero quantity")
        if pd.isna(row.Unit_price):
            problems.append("missing unit price")
        elif row.Unit_price <= 0:
            problems.append("non-positive unit price")
        if pd.isna(row.Discount_amount) or row.Discount_amount < 0:
            problems.append("missing/negative discount")
        elif not pd.isna(row.Quantity) and not pd.isna(row.Unit_price):
            if row.Discount_amount > row.Quantity * row.Unit_price:
                problems.append("discount exceeds gross line value")
        notes.append("; ".join(problems) if problems else None)
    df["data_quality_note"] = notes

    # --- Prepare for SQLite ---
    df["Order_date"] = df["Order_date"].dt.strftime("%Y-%m-%d")
    df["Quantity"] = df["Quantity"].fillna(-1).astype(int)
    df["Discount_amount"] = df["Discount_amount"].fillna(0.0)
    # Unit_price remains NULL when absent so revenue_filter() excludes the row.
    df = df.where(pd.notna(df), None)

    # --- Distinct value counts for the summary ---
    distinct_products = int(df["Product"].nunique())
    distinct_categories = int(df["Category"].nunique())
    distinct_regions = int(df["Region"].nunique())
    distinct_channels = int(df["Sales_channel"].nunique())
    statuses = df["Status"].value_counts().to_dict()
    date_range_min = df["Order_date"].min()
    date_range_max = df["Order_date"].max()

    # --- Write to SQLite ---
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        # Rebuild from the supplied CSV so re-runs don't retain stale data.
        conn.execute("DELETE FROM sales")
        conn.executemany(
            """INSERT INTO sales (
                transaction_id, order_date, product, category, region, sales_channel,
                quantity, unit_price, discount_amount, status, data_quality_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    str(r.Transaction_Id), str(r.Order_date), str(r.Product),
                    str(r.Category), str(r.Region), str(r.Sales_channel),
                    int(r.Quantity),
                    None if r.Unit_price is None else float(r.Unit_price),
                    float(r.Discount_amount), str(r.Status),
                    None if r.data_quality_note is None else str(r.data_quality_note),
                )
                for r in df.itertuples(index=False)
            ],
        )

    flagged_count = int(df["data_quality_note"].notna().sum())
    logger.info(
        "Ingestion complete: %d rows loaded, %d flagged, %d dropped, %d duplicates removed",
        len(df), flagged_count, dropped_mandatory, duplicates_removed,
    )

    return {
        "loaded_rows": len(df),
        "original_csv_rows": original_row_count,
        "dropped_mandatory_missing": dropped_mandatory,
        "duplicates_removed": duplicates_removed,
        "flagged_rows": flagged_count,
        "distinct_products": distinct_products,
        "distinct_categories": distinct_categories,
        "distinct_regions": distinct_regions,
        "distinct_channels": distinct_channels,
        "statuses": statuses,
        "date_range": f"{date_range_min} to {date_range_max}",
    }


# ---------------------------------------------------------------------------
# Revenue filter predicate
# ---------------------------------------------------------------------------

def revenue_filter() -> str:
    """SQL WHERE clause fragment: only completed transactions with usable numerics.

    Returned transactions and rows with missing/zero/negative prices or
    quantities are excluded from revenue calculations.
    """
    return (
        "LOWER(status) = 'completed' "
        "AND quantity > 0 "
        "AND unit_price IS NOT NULL "
        "AND unit_price > 0 "
        "AND discount_amount >= 0 "
        "AND discount_amount <= quantity * unit_price"
    )


# ---------------------------------------------------------------------------
# Data-quality summary
# ---------------------------------------------------------------------------

def get_data_quality_summary() -> dict:
    """Return a summary of data quality issues in the loaded dataset."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        flagged = conn.execute(
            "SELECT COUNT(*) FROM sales WHERE data_quality_note IS NOT NULL"
        ).fetchone()[0]
        returned = conn.execute(
            "SELECT COUNT(*) FROM sales WHERE LOWER(status) = 'returned'"
        ).fetchone()[0]
        valid_revenue_rows = conn.execute(
            f"SELECT COUNT(*) FROM sales WHERE {revenue_filter()}"
        ).fetchone()[0]
        flagged_details = [
            dict(r)
            for r in conn.execute(
                "SELECT transaction_id, data_quality_note FROM sales "
                "WHERE data_quality_note IS NOT NULL"
            ).fetchall()
        ]
    return {
        "total_rows": total,
        "flagged_rows": flagged,
        "returned_rows_excluded": returned,
        "valid_revenue_rows": valid_revenue_rows,
        "flagged_details": flagged_details,
    }
