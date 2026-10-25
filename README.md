# Mini AI Business Intelligence Assistant

A small application for asking natural-language questions about sales transactions. FastAPI handles the API, SQLite stores the supplied CSV data, and Streamlit provides the user interface.

## Features

- Imports the supplied CSV into SQLite on backend startup.
- Handles missing/non-positive unit prices, invalid quantities and invalid discounts by flagging those rows.
- Supports five analytics intents: total revenue, top product, monthly revenue trend, top region, and comparison between two months.
- Returns a human-readable answer, supporting figures, a query explanation, and the interpretation method.
- Optional LLM intent extraction using an OpenAI-compatible API. Without `OPENAI_API_KEY`, a deterministic rule-based parser works without a paid service.
- The LLM never generates SQL. Only predefined read-only query templates run.
- Automated tests cover data loading, analytics, unsupported questions, and invalid month values.

## Revenue definition and data quality

Net line revenue is `quantity * unit_price - discount_amount`. Only `Completed` transactions with positive quantity, positive non-null unit price, and a valid discount not exceeding the gross line value are included in revenue. Returned transactions are excluded. Rows with missing or invalid numeric values are retained in the database where possible and marked with a `data_quality_note`; they are excluded from revenue calculations.

This is a deliberate conservative choice. Review the flagged records before using the results for financial reporting.

## Architecture

```text
CSV file
   |
   v
Pandas validation and normalization
   |
   v
SQLite sales table + data-quality notes
   |
User question
   |
   v
Optional LLM intent extraction
(or deterministic rule-based fallback)
   |
   v
Allowlisted intent validation
   |
   v
Predefined read-only SQL query templates
   |
   v
Structured JSON answer + supporting figures
   |
   v
Streamlit UI
```

## Setup

Compatible with **Python 3.9** or newer.

### 1. Create and activate a virtual environment

**Windows PowerShell**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the Backend API

From the project root:

```bash
python3 -m uvicorn main:app --reload --port 8000
```
*(or `uvicorn main:app --reload`)*

On first startup, the database automatically ingests `data/sales_data.csv` into `sales.db`. Interactive Swagger API documentation is available at `http://127.0.0.1:8000/docs`.

### 4. Start the User Interface in a second terminal

In a new terminal window or tab (with the virtual environment activated):

```bash
python3 -m streamlit run app.py
```
*(or `streamlit run app.py`)*

Open the local address printed by Streamlit (default: `http://localhost:8501`).

### Optional LLM mode

Copy `.env.example` to `.env`, set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`), and export those variables before launching the API. Never commit `.env` or API keys. Without an API key, the system automatically uses its built-in deterministic rule-based intent parser.

PowerShell example:
```powershell
$env:OPENAI_API_KEY="your-key"
$env:OPENAI_MODEL="gpt-4o-mini"
python -m uvicorn main:app --reload
```

## API examples

```bash
curl -X POST "http://127.0.0.1:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the total revenue?"}'
```

Example supported questions:
- What is the total revenue?
- Which product generated the highest revenue?
- What is the monthly revenue trend?
- Which region generated the highest sales?
- Compare January 2026 and February 2026 revenue.
- What is the revenue by category?
- Compare online vs retail sales channel revenue.
- Show me data quality summary.

## Run tests

```bash
python3 -m pytest -v
```

## AI Use & Development Process

Generative AI was used as an interactive pair-programming assistant to brainstorm system architecture, draft the intent-to-query pipeline, and establish test coverage. All business logic, mathematical definitions, and database constraints were manually reviewed, verified, and validated against the supplied dataset.

For the complete candidate reflection report covering tools used, architecture decisions, real debugging challenges solved, and future enhancements, see [AI_DEVELOPMENT_NOTES.md](AI_DEVELOPMENT_NOTES.md).

## Error handling and safety

- Invalid/unsupported questions receive a structured response instead of arbitrary SQL execution.
- The API validates question length using Pydantic.
- LLM output is parsed as JSON and checked against a fixed intent allowlist.
- Month values are validated as `YYYY-MM`.
- No LLM-generated SQL is executed and no destructive query is exposed.

## Known limitations

- The deterministic parser recognizes a limited set of phrasings; unfamiliar wording may be rejected.
- Month comparison currently assumes that an omitted year means 2026, matching the provided dataset.
- This is a small demonstration, not a production financial reporting system.
- The optional OpenAI mode requires a valid API key and may fall back to the rule-based parser if the call fails.
- Review data-quality flags and revenue assumptions with the business owner before using the figures for decisions.

## Suggested improvements with another day

- Add more question types and stronger natural-language date parsing.
- Add a data-quality page and filters for category, region, channel, and status.
- Add API integration tests and CI on GitHub Actions.
- Add deployment configuration and authentication if the app is exposed publicly.
