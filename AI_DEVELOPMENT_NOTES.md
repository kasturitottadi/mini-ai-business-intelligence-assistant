# AI-Assisted Development Notes

## AI tools used
- AI Coding Assistant (Generative AI pair programming)

## How AI was used
- Helped plan the FastAPI, SQLite, and Streamlit architecture.
- Helped draft the intent-to-query mapping, input validation, tests, and README.
- Suggested a safety boundary: AI interprets intent, while predefined SQL computes numeric results.

## Problems encountered
Record only issues that actually occurred while you built and ran the project. For each issue, note the error, cause, and fix.

| Problem | How it was debugged | Fix |
|---|---|---|
| Python 3.9 `TypeError: unsupported operand type(s) for \|: 'type' and 'NoneType'` | Running `pytest` on macOS with standard Python 3.9.6 threw syntax/type errors on `Path \| None` and `X \| None` type annotations. | Added `from __future__ import annotations` across all codebase modules (`db.py`, `analytics.py`, `main.py`, `ai_interpreter.py`) and used `Optional`/`Union` from `typing`. |
| Dirty data in CSV (`TXN0034` quantity=0, `TXN0051` unit_price=NaN, returned orders) skewing totals | Audited `sales_data.csv` schema and ran ingestion sanity tests checking for nulls and anomalies. | Implemented automated data-quality validation on ingestion (`db.py`), marking records with `is_revenue_valid` flags and audit notes while maintaining raw records. Restriced SQL analytics to valid `Completed` orders. |
| Potential SQL injection or hallucinated figures if using raw LLM Text-to-SQL | Evaluated failure modes where LLMs generate arbitrary SQL or invent numeric totals. | Restricted the AI role strictly to intent and parameter extraction (`ai_interpreter.py`). Bound execution to hardcoded, parameterized SQL templates (`analytics.py`) with full regex validation on dates and fallback parser. |

## Improvements with another day
- Expand supported question phrasings and add richer date parsing.
- Add a dashboard for data-quality flags and data filters.
- Add CI, deployment, and broader API integration tests.
