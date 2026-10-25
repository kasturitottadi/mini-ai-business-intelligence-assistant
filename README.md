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

Use Python 3.10 or newer.

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

### 3. Start the API

From the project root:

```bash
uvicorn main:app --reload
```

The first startup imports `data/sales_data.csv` into `sales.db`. API documentation is available at `http://127.0.0.1:8000/docs`.

### 4. Start the UI in a second terminal

Activate the same virtual environment, then run:

```bash
streamlit run app.py
```

Open the local address Streamlit prints. Keep the API terminal running.

### Optional LLM mode

Copy `.env.example` to `.env`, set `OPENAI_API_KEY` and optionally `OPENAI_MODEL`, then export those variables in your terminal before starting the API. Do not commit `.env` or API keys. Without the key, the app uses its local rule-based intent parser.

PowerShell example:
```powershell
$env:OPENAI_API_KEY="your-key"
$env:OPENAI_MODEL="gpt-4o-mini"
uvicorn main:app --reload
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

## Run tests

```bash
pytest -q
```

## AI use and development notes

This project can be developed with ChatGPT as an AI coding assistant. AI assistance was used to structure the application, draft the SQLite analytics, and design validation and tests. The developer should review the code, run it locally, and be able to explain every design choice. Add any actual debugging problems encountered during your own run before submission; do not claim to have encountered issues that did not occur.

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
