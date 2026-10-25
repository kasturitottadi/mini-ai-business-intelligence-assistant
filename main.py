"""FastAPI backend for the Mini AI Business Intelligence Assistant.

Endpoints
---------
GET  /health  — application health check and data-quality summary
POST /ask     — accept a natural-language question and return an answer
GET  /docs    — auto-generated Swagger UI (provided by FastAPI)

All numerical results are calculated by SQLite queries, never invented by an LLM.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai_interpreter import interpret_with_ai
from analytics import execute_intent
from db import get_data_quality_summary, initialize_database

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup / lifespan
# ---------------------------------------------------------------------------

_ingestion_summary: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    global _ingestion_summary
    try:
        _ingestion_summary = initialize_database()
        logger.info("Database initialized: %s", _ingestion_summary)
    except Exception as exc:
        logger.error("Database initialization failed: %s", exc)
        _ingestion_summary = {"error": str(exc)}
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Mini AI Business Intelligence Assistant",
    description=(
        "Ask natural-language questions about sales transactions. "
        "Answers are calculated from validated SQLite queries; "
        "the AI only interprets the user's intent."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow Streamlit (or any local frontend) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class QuestionRequest(BaseModel):
    """Body for the POST /ask endpoint."""
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="A natural-language question about sales data.",
        examples=["What is the total revenue?"],
    )


class AnalyticsResponse(BaseModel):
    """Structured response from the POST /ask endpoint."""
    ok: bool
    question: str
    intent: str
    answer: str
    supporting_data: list[Any] = []
    interpretation_method: str
    sql_description: str = ""


class HealthResponse(BaseModel):
    """Structured response from the GET /health endpoint."""
    status: str
    ingestion_summary: dict = {}
    data_quality: dict = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health():
    """Check application health, ingestion status, and data quality."""
    try:
        dq = get_data_quality_summary()
    except Exception as exc:
        logger.error("Data quality check failed: %s", exc)
        dq = {"error": str(exc)}

    return HealthResponse(
        status="ok",
        ingestion_summary=_ingestion_summary,
        data_quality=dq,
    )


@app.post("/ask", response_model=AnalyticsResponse, tags=["Analytics"])
def ask(request: QuestionRequest):
    """Accept a natural-language question and return an analytics answer.

    The question is first interpreted (by LLM or deterministic fallback),
    then mapped to a predefined, safe SQL query.  The actual result is
    calculated by the database — never by the LLM.
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    try:
        parsed, method = interpret_with_ai(question)
    except Exception as exc:
        logger.error("Intent interpretation failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to interpret the question. Please try again.",
        )

    try:
        result = execute_intent(parsed)
    except Exception as exc:
        logger.error("Analytics execution failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to execute the analytics query. Please try again.",
        )

    return AnalyticsResponse(
        ok=result.get("ok", False),
        question=question,
        intent=result.get("intent", "unknown"),
        answer=result.get("answer", "No answer available."),
        supporting_data=result.get("supporting_data", []),
        interpretation_method=method,
        sql_description=result.get("sql_description", ""),
    )
