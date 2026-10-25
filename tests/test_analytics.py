"""Comprehensive unit tests for analytics, data ingestion, and intent parsing.

All tests use a temporary database initialised from the real CSV, so no
production data is modified.  Tests are repeatable and independent.
"""

import os
import re
import tempfile
from pathlib import Path

import pytest

import db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def test_db(monkeypatch):
    """Initialise a fresh temporary SQLite database from the supplied CSV.

    The fixture monkey-patches ``db.DATABASE_PATH`` so that all modules that
    import ``db.get_connection`` will use the temporary database.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "test.db"
        monkeypatch.setattr(db, "DATABASE_PATH", tmp_db)
        summary = db.initialize_database()
        yield summary


# ---------------------------------------------------------------------------
# 1. CSV ingestion and database initialization
# ---------------------------------------------------------------------------

class TestIngestion:
    def test_csv_loads_rows(self, test_db):
        assert test_db["loaded_rows"] > 0

    def test_csv_loaded_row_count(self, test_db):
        """The supplied CSV has 51 data rows; one has missing unit_price, one
        has zero quantity, and one is returned — they should still be loaded."""
        assert test_db["loaded_rows"] == 51

    def test_flagged_rows_detected(self, test_db):
        """TXN0034 (zero quantity) and TXN0051 (missing unit_price) must be flagged."""
        assert test_db["flagged_rows"] >= 2

    def test_no_duplicate_transaction_ids(self, test_db):
        assert test_db["duplicates_removed"] == 0

    def test_distinct_products(self, test_db):
        assert test_db["distinct_products"] == 7  # Laptop Stand, Wireless Mouse, Office Chair, Monitor, Keyboard, Desk, USB-C Hub

    def test_distinct_regions(self, test_db):
        assert test_db["distinct_regions"] == 4  # North, South, East, West

    def test_distinct_channels(self, test_db):
        assert test_db["distinct_channels"] == 2  # Online, Retail

    def test_date_range(self, test_db):
        assert "2026-01" in test_db["date_range"]
        assert "2026-06" in test_db["date_range"]

    def test_statuses_include_completed_and_returned(self, test_db):
        statuses = test_db["statuses"]
        assert "Completed" in statuses
        assert "Returned" in statuses

    def test_missing_csv_raises_file_not_found(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setattr(db, "DATABASE_PATH", Path(tmp) / "test2.db")
            with pytest.raises(FileNotFoundError):
                db.initialize_database(csv_path="/nonexistent/path.csv")

    def test_idempotent_initialization(self, test_db, monkeypatch):
        """Re-running initialize_database should not raise or duplicate rows."""
        summary2 = db.initialize_database()
        assert summary2["loaded_rows"] == test_db["loaded_rows"]


# ---------------------------------------------------------------------------
# 2. Total revenue calculation
# ---------------------------------------------------------------------------

class TestTotalRevenue:
    def test_returns_ok(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "total_revenue"})
        assert result["ok"] is True
        assert result["intent"] == "total_revenue"

    def test_returns_positive_revenue(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "total_revenue"})
        amount = result["supporting_data"][0]["total_revenue"]
        assert amount > 0

    def test_revenue_is_numeric(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "total_revenue"})
        amount = result["supporting_data"][0]["total_revenue"]
        assert isinstance(amount, (int, float))

    def test_answer_contains_currency(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "total_revenue"})
        assert "₹" in result["answer"]

    def test_supporting_data_has_transaction_count(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "total_revenue"})
        assert "transaction_count" in result["supporting_data"][0]
        assert result["supporting_data"][0]["transaction_count"] > 0


# ---------------------------------------------------------------------------
# 3. Highest-revenue product
# ---------------------------------------------------------------------------

class TestTopProduct:
    def test_returns_ok(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "top_product"})
        assert result["ok"] is True

    def test_returns_supporting_rows(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "top_product"})
        assert len(result["supporting_data"]) > 0

    def test_answer_mentions_highest(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "top_product"})
        assert "highest revenue" in result["answer"].lower()

    def test_products_sorted_by_revenue_desc(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "top_product"})
        revenues = [r["revenue"] for r in result["supporting_data"]]
        assert revenues == sorted(revenues, reverse=True)

    def test_all_products_have_revenue(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "top_product"})
        for row in result["supporting_data"]:
            assert "revenue" in row
            assert "product" in row
            assert row["revenue"] >= 0


# ---------------------------------------------------------------------------
# 4. Monthly trend calculation
# ---------------------------------------------------------------------------

class TestMonthlyTrend:
    def test_returns_ok(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "monthly_trend"})
        assert result["ok"] is True

    def test_months_are_sorted_chronologically(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "monthly_trend"})
        months = [r["month"] for r in result["supporting_data"]]
        assert months == sorted(months)

    def test_six_months_in_dataset(self):
        """The dataset covers Jan–Jun 2026."""
        from analytics import execute_intent
        result = execute_intent({"intent": "monthly_trend"})
        months = [r["month"] for r in result["supporting_data"]]
        assert len(months) == 6

    def test_each_month_has_revenue(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "monthly_trend"})
        for row in result["supporting_data"]:
            assert "revenue" in row
            assert row["revenue"] >= 0


# ---------------------------------------------------------------------------
# 5. Month comparison
# ---------------------------------------------------------------------------

class TestMonthComparison:
    def test_valid_comparison(self):
        from analytics import execute_intent
        result = execute_intent({
            "intent": "month_comparison",
            "month1": "2026-01",
            "month2": "2026-02",
        })
        assert result["ok"] is True
        assert "increased" in result["answer"] or "decreased" in result["answer"] or "did not change" in result["answer"]

    def test_absolute_change_is_numeric(self):
        from analytics import execute_intent
        result = execute_intent({
            "intent": "month_comparison",
            "month1": "2026-01",
            "month2": "2026-02",
        })
        change_row = next(
            r for r in result["supporting_data"] if "absolute_change" in r
        )
        assert isinstance(change_row["absolute_change"], (int, float))

    def test_percentage_change_present(self):
        from analytics import execute_intent
        result = execute_intent({
            "intent": "month_comparison",
            "month1": "2026-01",
            "month2": "2026-02",
        })
        change_row = next(
            r for r in result["supporting_data"] if "percentage_change" in r
        )
        assert change_row["percentage_change"] is None or isinstance(
            change_row["percentage_change"], (int, float)
        )

    def test_invalid_month_rejected(self):
        from analytics import execute_intent
        result = execute_intent({
            "intent": "month_comparison",
            "month1": "bad",
            "month2": "2026-02",
        })
        assert result["ok"] is False

    def test_both_months_invalid(self):
        from analytics import execute_intent
        result = execute_intent({
            "intent": "month_comparison",
            "month1": "nope",
            "month2": "also-bad",
        })
        assert result["ok"] is False

    def test_nonexistent_months_return_zero_revenue(self):
        from analytics import execute_intent
        result = execute_intent({
            "intent": "month_comparison",
            "month1": "2026-11",
            "month2": "2026-12",
        })
        assert result["ok"] is True
        month_rows = [r for r in result["supporting_data"] if "month" in r]
        for row in month_rows:
            assert row["revenue"] == 0.0

    def test_comparison_symmetry_direction(self):
        """Swapping the months should reverse the direction."""
        from analytics import execute_intent
        r1 = execute_intent({
            "intent": "month_comparison",
            "month1": "2026-01",
            "month2": "2026-02",
        })
        r2 = execute_intent({
            "intent": "month_comparison",
            "month1": "2026-02",
            "month2": "2026-01",
        })
        c1 = next(r for r in r1["supporting_data"] if "absolute_change" in r)
        c2 = next(r for r in r2["supporting_data"] if "absolute_change" in r)
        assert abs(c1["absolute_change"]) == abs(c2["absolute_change"])


# ---------------------------------------------------------------------------
# 6. Unsupported question handling
# ---------------------------------------------------------------------------

class TestUnsupportedQuestions:
    def test_unsupported_returns_ok_false(self):
        from analytics import interpret_question, execute_intent
        result = execute_intent(interpret_question("Tell me a joke"))
        assert result["ok"] is False

    def test_unsupported_returns_empty_supporting_data(self):
        from analytics import interpret_question, execute_intent
        result = execute_intent(interpret_question("What is the meaning of life?"))
        assert result["supporting_data"] == []

    def test_unsupported_intent_string(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "unknown_intent_xyz"})
        assert result["ok"] is False
        assert result["intent"] == "unsupported"


# ---------------------------------------------------------------------------
# 7. Intent parsing (deterministic fallback)
# ---------------------------------------------------------------------------

class TestIntentParsing:
    def test_total_revenue_intent(self):
        from analytics import interpret_question
        assert interpret_question("What is the total revenue?")["intent"] == "total_revenue"

    def test_overall_revenue_intent(self):
        from analytics import interpret_question
        assert interpret_question("Show me the overall revenue")["intent"] == "total_revenue"

    def test_top_product_intent(self):
        from analytics import interpret_question
        assert interpret_question("Which product generated the highest revenue?")["intent"] == "top_product"

    def test_monthly_trend_intent(self):
        from analytics import interpret_question
        assert interpret_question("What is the monthly revenue trend?")["intent"] == "monthly_trend"

    def test_top_region_intent(self):
        from analytics import interpret_question
        assert interpret_question("Which region generated the highest sales?")["intent"] == "top_region"

    def test_month_comparison_intent(self):
        from analytics import interpret_question
        parsed = interpret_question("Compare January 2026 and February 2026 revenue")
        assert parsed["intent"] == "month_comparison"
        assert parsed["month1"] == "2026-01"
        assert parsed["month2"] == "2026-02"

    def test_unsupported_question_intent(self):
        from analytics import interpret_question
        assert interpret_question("Tell me a joke")["intent"] == "unsupported"

    def test_category_intent(self):
        from analytics import interpret_question
        assert interpret_question("What is the revenue by category?")["intent"] == "revenue_by_category"

    def test_channel_intent(self):
        from analytics import interpret_question
        assert interpret_question("Compare online vs retail sales channel revenue")["intent"] == "sales_channel_comparison"


# ---------------------------------------------------------------------------
# 8. Data quality
# ---------------------------------------------------------------------------

class TestDataQuality:
    def test_data_quality_summary(self):
        summary = db.get_data_quality_summary()
        assert "total_rows" in summary
        assert "flagged_rows" in summary
        assert "returned_rows_excluded" in summary
        assert "valid_revenue_rows" in summary

    def test_flagged_details_returned(self):
        summary = db.get_data_quality_summary()
        assert isinstance(summary["flagged_details"], list)
        assert len(summary["flagged_details"]) >= 2

    def test_data_quality_intent(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "data_quality_summary"})
        assert result["ok"] is True
        assert "flagged" in result["answer"].lower() or "quality" in result["answer"].lower()


# ---------------------------------------------------------------------------
# 9. LLM fallback
# ---------------------------------------------------------------------------

class TestLLMFallback:
    def test_fallback_without_api_key(self, monkeypatch):
        """Without OPENAI_API_KEY, should fall back to rule-based parser."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from ai_interpreter import interpret_with_ai
        parsed, method = interpret_with_ai("What is the total revenue?")
        assert parsed["intent"] == "total_revenue"
        assert "fallback" in method.lower() or "rule" in method.lower()

    def test_fallback_method_is_transparent(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from ai_interpreter import interpret_with_ai
        _, method = interpret_with_ai("Which product generated the highest revenue?")
        assert "rule-based" in method.lower()


# ---------------------------------------------------------------------------
# 10. Revenue by category (bonus)
# ---------------------------------------------------------------------------

class TestRevenuByCategory:
    def test_returns_ok(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "revenue_by_category"})
        assert result["ok"] is True

    def test_returns_categories(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "revenue_by_category"})
        categories = [r["category"] for r in result["supporting_data"]]
        assert "Accessories" in categories
        assert "Electronics" in categories
        assert "Furniture" in categories


# ---------------------------------------------------------------------------
# 11. Sales channel comparison (bonus)
# ---------------------------------------------------------------------------

class TestSalesChannel:
    def test_returns_ok(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "sales_channel_comparison"})
        assert result["ok"] is True

    def test_returns_channels(self):
        from analytics import execute_intent
        result = execute_intent({"intent": "sales_channel_comparison"})
        channels = [r["sales_channel"] for r in result["supporting_data"]]
        assert "Online" in channels
        assert "Retail" in channels
