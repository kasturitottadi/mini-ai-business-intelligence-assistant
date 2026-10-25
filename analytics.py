from __future__ import annotations

"""Deterministic analytics — all numeric answers are calculated by SQLite.

Every public function returns a dict with:
  ok             – bool
  intent         – str
  answer         – str (human-readable answer)
  supporting_data – list[dict]
  sql_description – str (plain-English query explanation)

Revenue definition:
  Net revenue = quantity × unit_price − discount_amount
  Only rows matching ``db.revenue_filter()`` are included.
"""

import re
from db import get_connection, revenue_filter

# ---------------------------------------------------------------------------
# Supported intents (allowlist)
# ---------------------------------------------------------------------------

SUPPORTED_INTENTS = {
    "total_revenue",
    "top_product",
    "monthly_trend",
    "top_region",
    "month_comparison",
    "revenue_by_category",
    "sales_channel_comparison",
    "data_quality_summary",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a read-only query and return results as a list of dicts."""
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _month_from_text(text: str) -> list[str]:
    """Extract YYYY-MM month strings from question text.

    Handles:
    - Explicit YYYY-MM or YYYY/MM patterns
    - Month names like 'January', 'Feb' etc.  with optional year
    - Defaults year to 2026 (the dataset year) if not specified
    """
    q = text.lower()
    month_names = {
        "january": "01", "jan": "01",
        "february": "02", "feb": "02",
        "march": "03", "mar": "03",
        "april": "04", "apr": "04",
        "may": "05",
        "june": "06", "jun": "06",
        "july": "07", "jul": "07",
        "august": "08", "aug": "08",
        "september": "09", "sep": "09", "sept": "09",
        "october": "10", "oct": "10",
        "november": "11", "nov": "11",
        "december": "12", "dec": "12",
    }
    found: list[str] = []

    # Explicit YYYY-MM patterns
    for m in re.finditer(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", q):
        found.append(f"{m.group(1)}-{int(m.group(2)):02d}")

    # Month names
    for name, number in month_names.items():
        if re.search(rf"\b{name}\b", q):
            # Look for an explicit year near the month name
            years = re.findall(r"\b20\d{2}\b", q)
            found.append(f"{years[0] if years else '2026'}-{number}")

    # Deduplicate while preserving order
    return list(dict.fromkeys(found))


# ---------------------------------------------------------------------------
# Intent parser (deterministic fallback)
# ---------------------------------------------------------------------------

def interpret_question(question: str) -> dict:
    """Small, transparent rule-based intent parser.

    Optional LLM interpretation lives in ``ai_interpreter.py`` and takes
    precedence when an API key is available.
    """
    q = question.lower().strip()
    months = _month_from_text(q)

    # --- total revenue ---
    if any(x in q for x in [
        "total revenue", "overall revenue", "revenue in total",
        "total sales", "total net revenue", "how much revenue",
    ]):
        return {"intent": "total_revenue"}

    # --- top product ---
    if ("highest" in q or "top" in q or "best" in q or "most" in q) and \
       any(x in q for x in ["product", "item"]):
        return {"intent": "top_product"}

    # --- monthly trend ---
    if any(x in q for x in [
        "monthly revenue trend", "monthly trend", "revenue trend",
        "trend by month", "revenue each month", "month by month",
        "monthly revenue", "monthly sales trend",
    ]):
        return {"intent": "monthly_trend"}

    # --- top region ---
    if ("highest" in q or "top" in q or "best" in q or "most" in q) and \
       any(x in q for x in ["region", "sales by region", "regional", "area"]):
        return {"intent": "top_region"}

    # --- month comparison ---
    if any(x in q for x in [
        "change between", "compare", "comparison", "difference between",
        "changed from", "versus", "vs",
    ]) and len(months) >= 2:
        return {"intent": "month_comparison", "month1": months[0], "month2": months[1]}

    # Implicit month comparison when two months and 'revenue' mentioned
    if "revenue" in q and len(months) >= 2:
        return {"intent": "month_comparison", "month1": months[0], "month2": months[1]}

    # --- revenue by category ---
    if any(x in q for x in ["category", "categories"]) and \
       any(x in q for x in ["revenue", "sales", "breakdown"]):
        return {"intent": "revenue_by_category"}

    # --- sales channel comparison ---
    if any(x in q for x in ["channel", "online", "retail"]) and \
       any(x in q for x in ["revenue", "sales", "compare", "comparison", "breakdown"]):
        return {"intent": "sales_channel_comparison"}

    # --- data quality ---
    if any(x in q for x in ["data quality", "data issues", "flagged", "invalid"]):
        return {"intent": "data_quality_summary"}

    # Single month with revenue
    if "revenue" in q and len(months) == 1:
        return {"intent": "monthly_trend", "month": months[0]}

    return {"intent": "unsupported"}


# ---------------------------------------------------------------------------
# Intent execution
# ---------------------------------------------------------------------------

def _unsupported_result() -> dict:
    return {
        "ok": False,
        "intent": "unsupported",
        "answer": (
            "I couldn't map that question to a supported analysis. "
            "Try asking about total revenue, top product, monthly revenue trend, "
            "top region, comparing two months, revenue by category, or sales channel comparison."
        ),
        "supporting_data": [],
        "sql_description": "No query executed.",
    }


def execute_intent(parsed: dict) -> dict:
    """Execute the analytics operation corresponding to the parsed intent."""
    intent = parsed.get("intent")

    if intent not in SUPPORTED_INTENTS:
        return _unsupported_result()

    where = revenue_filter()

    # -----------------------------------------------------------------
    # Total revenue
    # -----------------------------------------------------------------
    if intent == "total_revenue":
        rows = _query(
            f"""SELECT
                    ROUND(COALESCE(SUM(quantity * unit_price - discount_amount), 0), 2)
                        AS total_revenue,
                    COUNT(*) AS transaction_count,
                    SUM(quantity) AS total_units_sold,
                    ROUND(COALESCE(SUM(discount_amount), 0), 2) AS total_discount
                FROM sales
                WHERE {where}"""
        )
        r = rows[0]
        amount = r["total_revenue"]
        return {
            "ok": True,
            "intent": intent,
            "answer": (
                f"Total recognized net revenue is ₹{amount:,.2f} "
                f"across {r['transaction_count']} completed transactions "
                f"({r['total_units_sold']} units sold, ₹{r['total_discount']:,.2f} in discounts)."
            ),
            "supporting_data": rows,
            "sql_description": (
                "Sum (quantity × unit_price − discount_amount) for all completed "
                "transactions with valid positive quantities, positive unit prices, "
                "and valid discounts."
            ),
        }

    # -----------------------------------------------------------------
    # Top product by revenue
    # -----------------------------------------------------------------
    if intent == "top_product":
        rows = _query(
            f"""SELECT
                    product,
                    ROUND(SUM(quantity * unit_price - discount_amount), 2) AS revenue,
                    SUM(quantity) AS units_sold,
                    COUNT(*) AS transactions
                FROM sales
                WHERE {where}
                GROUP BY product
                ORDER BY revenue DESC, product ASC
                LIMIT 10"""
        )
        if not rows:
            return {
                "ok": True, "intent": intent,
                "answer": "No valid completed sales were found.",
                "supporting_data": [],
                "sql_description": "Group valid completed sales by product and sort by revenue.",
            }
        first = rows[0]
        return {
            "ok": True, "intent": intent,
            "answer": (
                f"{first['product']} generated the highest revenue at ₹{first['revenue']:,.2f} "
                f"({first['units_sold']} units across {first['transactions']} transactions)."
            ),
            "supporting_data": rows,
            "sql_description": (
                "Group valid completed sales by product, calculate net revenue, "
                "and sort by revenue descending."
            ),
        }

    # -----------------------------------------------------------------
    # Monthly revenue trend
    # -----------------------------------------------------------------
    if intent == "monthly_trend":
        rows = _query(
            f"""SELECT
                    substr(order_date, 1, 7) AS month,
                    ROUND(SUM(quantity * unit_price - discount_amount), 2) AS revenue,
                    COUNT(*) AS transaction_count,
                    SUM(quantity) AS units_sold
                FROM sales
                WHERE {where}
                GROUP BY substr(order_date, 1, 7)
                ORDER BY month"""
        )
        if not rows:
            return {
                "ok": True, "intent": intent,
                "answer": "No valid completed sales were found for the monthly trend.",
                "supporting_data": [],
                "sql_description": "Group valid completed sales by year-month.",
            }
        months_text = ", ".join(
            f"{r['month']}: ₹{r['revenue']:,.2f}" for r in rows
        )
        return {
            "ok": True, "intent": intent,
            "answer": f"Monthly revenue trend (completed transactions): {months_text}.",
            "supporting_data": rows,
            "sql_description": (
                "Group valid completed sales by year-month and sum "
                "(quantity × unit_price − discount_amount)."
            ),
        }

    # -----------------------------------------------------------------
    # Top region
    # -----------------------------------------------------------------
    if intent == "top_region":
        rows = _query(
            f"""SELECT
                    region,
                    ROUND(SUM(quantity * unit_price - discount_amount), 2) AS revenue,
                    SUM(quantity) AS units_sold,
                    COUNT(*) AS transactions
                FROM sales
                WHERE {where}
                GROUP BY region
                ORDER BY revenue DESC, region ASC"""
        )
        if not rows:
            return {
                "ok": True, "intent": intent,
                "answer": "No valid completed sales were found.",
                "supporting_data": [],
                "sql_description": "Group valid completed sales by region and sort by revenue.",
            }
        first = rows[0]
        return {
            "ok": True, "intent": intent,
            "answer": (
                f"{first['region']} generated the highest sales revenue at ₹{first['revenue']:,.2f} "
                f"({first['units_sold']} units across {first['transactions']} transactions)."
            ),
            "supporting_data": rows,
            "sql_description": (
                "Group valid completed sales by region and sort by revenue descending."
            ),
        }

    # -----------------------------------------------------------------
    # Month comparison
    # -----------------------------------------------------------------
    if intent == "month_comparison":
        m1 = parsed.get("month1")
        m2 = parsed.get("month2")
        month_pattern = r"20\d{2}-(0[1-9]|1[0-2])"
        if not re.fullmatch(month_pattern, str(m1)) or \
           not re.fullmatch(month_pattern, str(m2)):
            return {
                "ok": False, "intent": intent,
                "answer": (
                    "Please specify two valid months. Example: "
                    "Compare January 2026 and February 2026 revenue."
                ),
                "supporting_data": [],
                "sql_description": "No query executed — invalid month values.",
            }
        rows = _query(
            f"""SELECT
                    substr(order_date, 1, 7) AS month,
                    ROUND(SUM(quantity * unit_price - discount_amount), 2) AS revenue
                FROM sales
                WHERE {where} AND substr(order_date, 1, 7) IN (?, ?)
                GROUP BY substr(order_date, 1, 7)
                ORDER BY month""",
            (m1, m2),
        )
        values = {r["month"]: float(r["revenue"]) for r in rows}
        a, b = values.get(m1, 0.0), values.get(m2, 0.0)
        change = b - a
        if a == 0:
            pct = None
            pct_text = (
                "percentage change is undefined because the baseline month has zero revenue"
            )
        else:
            pct = (change / a) * 100
            direction_word = "increase" if pct >= 0 else "decrease"
            pct_text = f"a {abs(pct):.2f}% {direction_word}"

        if change > 0:
            direction = "increased"
        elif change < 0:
            direction = "decreased"
        else:
            direction = "did not change"

        answer = (
            f"Revenue {direction} by ₹{abs(change):,.2f} "
            f"from {m1} (₹{a:,.2f}) to {m2} (₹{b:,.2f}); {pct_text}."
        )
        return {
            "ok": True, "intent": intent,
            "answer": answer,
            "supporting_data": [
                {"month": m1, "revenue": a},
                {"month": m2, "revenue": b},
                {
                    "absolute_change": round(change, 2),
                    "percentage_change": None if pct is None else round(pct, 2),
                    "direction": direction,
                },
            ],
            "sql_description": (
                "Query valid completed revenue for the two specified months, "
                "then calculate absolute and percentage change."
            ),
        }

    # -----------------------------------------------------------------
    # Revenue by category (bonus insight)
    # -----------------------------------------------------------------
    if intent == "revenue_by_category":
        rows = _query(
            f"""SELECT
                    category,
                    ROUND(SUM(quantity * unit_price - discount_amount), 2) AS revenue,
                    SUM(quantity) AS units_sold,
                    COUNT(*) AS transactions
                FROM sales
                WHERE {where}
                GROUP BY category
                ORDER BY revenue DESC"""
        )
        if not rows:
            return {
                "ok": True, "intent": intent,
                "answer": "No valid completed sales were found.",
                "supporting_data": [],
                "sql_description": "Group valid completed sales by category.",
            }
        summary = ", ".join(f"{r['category']}: ₹{r['revenue']:,.2f}" for r in rows)
        return {
            "ok": True, "intent": intent,
            "answer": f"Revenue by category: {summary}.",
            "supporting_data": rows,
            "sql_description": "Group valid completed sales by category and sort by revenue.",
        }

    # -----------------------------------------------------------------
    # Sales channel comparison (bonus insight)
    # -----------------------------------------------------------------
    if intent == "sales_channel_comparison":
        rows = _query(
            f"""SELECT
                    sales_channel,
                    ROUND(SUM(quantity * unit_price - discount_amount), 2) AS revenue,
                    SUM(quantity) AS units_sold,
                    COUNT(*) AS transactions
                FROM sales
                WHERE {where}
                GROUP BY sales_channel
                ORDER BY revenue DESC"""
        )
        if not rows:
            return {
                "ok": True, "intent": intent,
                "answer": "No valid completed sales were found.",
                "supporting_data": [],
                "sql_description": "Group valid completed sales by sales channel.",
            }
        summary = ", ".join(f"{r['sales_channel']}: ₹{r['revenue']:,.2f}" for r in rows)
        return {
            "ok": True, "intent": intent,
            "answer": f"Revenue by sales channel: {summary}.",
            "supporting_data": rows,
            "sql_description": "Group valid completed sales by sales channel.",
        }

    # -----------------------------------------------------------------
    # Data quality summary (bonus insight)
    # -----------------------------------------------------------------
    if intent == "data_quality_summary":
        from db import get_data_quality_summary
        dq = get_data_quality_summary()
        return {
            "ok": True, "intent": intent,
            "answer": (
                f"The dataset has {dq['total_rows']} records. "
                f"{dq['flagged_rows']} rows have data-quality issues. "
                f"{dq['returned_rows_excluded']} rows are returned transactions (excluded from revenue). "
                f"{dq['valid_revenue_rows']} rows are valid for revenue calculations."
            ),
            "supporting_data": dq.get("flagged_details", []),
            "sql_description": "Count total, flagged, returned, and revenue-valid rows.",
        }

    return _unsupported_result()
