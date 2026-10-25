# AI-Assisted Development Notes

**Candidate Submission** — Mini AI Business Intelligence Assistant  
**Role:** Graduate Engineer Trainee Selection Challenge  
**Target Organization:** RSG Research Private Limited  

---

## 1. AI Tools Used
- **AI Coding Assistant (Claude / ChatGPT)**: Used as an interactive pair programmer for architectural brainstorming, boilerplate drafting, test generation, and debugging.

---

## 2. How AI Was Used in My Workflow
- **Architecture & System Design**: I collaborated with AI to establish the multi-tier architecture separating the FastAPI backend, SQLite analytical engine, and Streamlit frontend.
- **Architectural Boundary & Security**: I established a zero-trust AI computing boundary: rather than allowing the LLM to generate or execute arbitrary SQL (which creates SQL-injection risks and mathematical hallucinations), I used the AI exclusively for intent classification and parameter extraction (`YYYY-MM`). All mathematical calculations are executed by deterministic, parameterized SQLite queries.
- **Test Generation & Code Coverage**: I used AI to assist in creating a comprehensive test matrix of 73 unit and integration tests covering data ingestion, revenue calculations, invalid inputs, and edge cases.
- **Documentation**: I drafted the OpenAPI descriptions, architecture diagrams, and user guidance.

---

## 3. Problems Encountered and How I Resolved Them

| Problem | Root Cause & How I Debugged It | Resolution |
|---|---|---|
| **Python 3.9 Type Annotation Incompatibility** | When running `pytest` on macOS with standard Python 3.9, the runtime threw `TypeError: unsupported operand type(s) for \|: 'type' and 'NoneType'` on PEP 604 union syntax (`Path \| None`). | I diagnosed the issue as Python 3.9 syntax constraints and added `from __future__ import annotations` across `db.py`, `analytics.py`, `main.py`, and `ai_interpreter.py`, using `Optional` and `Union` from `typing` to guarantee backward compatibility. |
| **Data Quality Anomalies in CSV** | Auditing `sales_data.csv` revealed three data integrity issues: `TXN0034` had quantity=0, `TXN0051` had missing unit price, and `TXN0033` was a returned order. Treating them naively would distort financial figures. | I designed a data-quality pipeline in `db.py` that flags irregular records with `is_revenue_valid = 0` and descriptive audit notes, while preserving raw rows. In `analytics.py`, I strictly filtered revenue queries on `is_revenue_valid = 1 AND status = 'Completed'`, maintaining financial correctness without discarding transaction history. |
| **Preventing SQL Injections & Hallucinated Metrics** | Allowing an LLM to directly write SQL or calculate totals introduces security vulnerabilities and unreliable math. | I constrained the AI's role in `ai_interpreter.py` strictly to intent classification with schema validation, backed by an immediate deterministic fallback parser. The database handles all calculations deterministically. |
| **UI State Execution on Sidebar Example Selection** | In Streamlit, clicking sidebar buttons updated session state but did not immediately trigger execution unless the user manually navigated to and clicked "Analyze". | I refactored the UI state management in `app.py` so selecting any sample question immediately initiates the analytics call and renders the KPI metrics, Plotly chart, and supporting data without extra user clicks. |

---

## 4. What I Would Improve With Another Day of Work
1. **GitHub Actions CI/CD**: Add an automated workflow to execute `pytest` on push and pull requests across Python 3.9, 3.10, 3.11, and 3.12.
2. **Multi-Turn Conversational Context**: Enhance the intent classifier to remember previous questions (e.g., asking *"What about in the South region?"* following a total revenue query).
3. **Advanced Visual Filters**: Add sidebar interactive filters in Streamlit allowing business users to slice data by custom date ranges, payment channels, and product categories.
4. **Containerization**: Provide a multi-stage `Dockerfile` and `docker-compose.yml` to spin up both the FastAPI backend and Streamlit UI in isolated containers with a single command.

