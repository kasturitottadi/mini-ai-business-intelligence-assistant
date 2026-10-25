"""API integration tests for the FastAPI backend.

These tests use the FastAPI ``TestClient`` (backed by HTTPX) to test the
``/health`` and ``/ask`` endpoints without starting a real server.

A temporary database is used so that production data is never modified.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import db


@pytest.fixture(autouse=True)
def test_db(monkeypatch):
    """Use a temporary database for all API tests."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "test_api.db"
        monkeypatch.setattr(db, "DATABASE_PATH", tmp_db)
        db.initialize_database()
        yield


@pytest.fixture()
def client():
    """Create a TestClient that skips the lifespan (DB already initialised)."""
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_includes_data_quality(self, client):
        data = client.get("/health").json()
        assert "data_quality" in data
        assert "total_rows" in data["data_quality"]


# ---------------------------------------------------------------------------
# /ask endpoint — valid questions
# ---------------------------------------------------------------------------

class TestAskEndpoint:
    def test_total_revenue(self, client):
        response = client.post("/ask", json={"question": "What is the total revenue?"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["intent"] == "total_revenue"
        assert "₹" in data["answer"]

    def test_top_product(self, client):
        response = client.post("/ask", json={"question": "Which product generated the highest revenue?"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["intent"] == "top_product"

    def test_monthly_trend(self, client):
        response = client.post("/ask", json={"question": "What is the monthly revenue trend?"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["intent"] == "monthly_trend"
        assert len(data["supporting_data"]) > 0

    def test_top_region(self, client):
        response = client.post("/ask", json={"question": "Which region generated the highest sales?"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["intent"] == "top_region"

    def test_month_comparison(self, client):
        response = client.post(
            "/ask",
            json={"question": "Compare January 2026 and February 2026 revenue."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["intent"] == "month_comparison"

    def test_response_includes_interpretation_method(self, client):
        response = client.post("/ask", json={"question": "What is the total revenue?"})
        data = response.json()
        assert "interpretation_method" in data
        assert data["interpretation_method"]  # non-empty

    def test_response_includes_question(self, client):
        q = "Which product generated the highest revenue?"
        response = client.post("/ask", json={"question": q})
        data = response.json()
        assert data["question"] == q

    def test_response_includes_sql_description(self, client):
        response = client.post("/ask", json={"question": "What is the total revenue?"})
        data = response.json()
        assert "sql_description" in data
        assert len(data["sql_description"]) > 0


# ---------------------------------------------------------------------------
# /ask endpoint — unsupported and invalid inputs
# ---------------------------------------------------------------------------

class TestAskValidation:
    def test_unsupported_question_returns_ok_false(self, client):
        response = client.post("/ask", json={"question": "Tell me a joke about databases"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["intent"] == "unsupported"

    def test_empty_question_rejected(self, client):
        response = client.post("/ask", json={"question": ""})
        assert response.status_code == 422  # Pydantic validation

    def test_too_short_question_rejected(self, client):
        response = client.post("/ask", json={"question": "Hi"})
        assert response.status_code == 422

    def test_missing_question_field(self, client):
        response = client.post("/ask", json={})
        assert response.status_code == 422

    def test_invalid_json_body(self, client):
        response = client.post(
            "/ask",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_whitespace_only_question(self, client):
        response = client.post("/ask", json={"question": "     "})
        # Should be rejected either by Pydantic (min_length) or endpoint logic
        assert response.status_code in (422, 200)

    def test_very_long_question_rejected(self, client):
        long_q = "What is the total revenue? " * 100  # >500 chars
        response = client.post("/ask", json={"question": long_q})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# /ask endpoint — response structure
# ---------------------------------------------------------------------------

class TestResponseStructure:
    def test_all_required_fields_present(self, client):
        response = client.post("/ask", json={"question": "What is the total revenue?"})
        data = response.json()
        required_fields = {"ok", "question", "intent", "answer", "supporting_data",
                           "interpretation_method", "sql_description"}
        assert required_fields.issubset(data.keys())

    def test_supporting_data_is_list(self, client):
        response = client.post("/ask", json={"question": "What is the total revenue?"})
        data = response.json()
        assert isinstance(data["supporting_data"], list)
