"""Optional LLM intent interpretation.

The LLM is used **only** to extract a structured intent from the user's
natural-language question.  It never generates SQL, never calculates numbers,
and never supplies financial figures.

When the ``OPENAI_API_KEY`` environment variable is not set or an API error
occurs, the system transparently falls back to the deterministic rule-based
parser in ``analytics.interpret_question``.

Security rules applied to every LLM response
---------------------------------------------
1. The extracted ``intent`` must belong to ``SUPPORTED_INTENTS``.
2. Month parameters must match ``YYYY-MM`` format.
3. Malformed or unexpected JSON is caught and triggers fallback.
4. No LLM-generated SQL is ever executed.
"""

from __future__ import annotations

import json
import logging
import os
import re

from analytics import SUPPORTED_INTENTS, interpret_question

logger = logging.getLogger(__name__)

# Maximum question length to send to the LLM
MAX_QUESTION_LENGTH = 500

# System prompt — instructs the model to return JSON only
_SYSTEM_PROMPT = (
    "You are a sales analytics intent classifier. "
    "Extract the user's intent from a natural-language question about sales data.\n\n"
    "Return **only** a JSON object. Do NOT include any explanation or markdown.\n\n"
    "Allowed intents:\n"
    "  total_revenue — overall revenue\n"
    "  top_product — product with the highest revenue\n"
    "  monthly_trend — revenue trend by month\n"
    "  top_region — region with the highest sales\n"
    "  month_comparison — compare revenue between two months "
    "(include \"month1\" and \"month2\" as YYYY-MM)\n"
    "  revenue_by_category — revenue breakdown by product category\n"
    "  sales_channel_comparison — online vs retail revenue\n"
    "  data_quality_summary — information about data quality\n"
    "  unsupported — if the question does not match any above\n\n"
    "Dataset dates are in 2026 unless the user specifies a different year.\n\n"
    "Example outputs:\n"
    '  {\"intent\": \"total_revenue\"}\n'
    '  {\"intent\": \"month_comparison\", \"month1\": \"2026-01\", \"month2\": \"2026-02\"}\n'
    '  {\"intent\": \"unsupported\"}\n\n'
    "NEVER generate SQL. If unsure, return {\"intent\": \"unsupported\"}."
)


def interpret_with_ai(question: str) -> tuple[dict, str]:
    """Try LLM-based intent extraction; fall back to the rule-based parser.

    Returns
    -------
    (parsed_intent, interpretation_method)
        ``parsed_intent`` is a dict with at least an ``"intent"`` key.
        ``interpretation_method`` is a human-readable label describing which
        method was used.
    """
    # Truncate excessively long questions
    question = question[:MAX_QUESTION_LENGTH]

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.debug("No OPENAI_API_KEY — using rule-based fallback.")
        return interpret_question(question), "rule-based fallback (no API key)"

    try:
        from openai import OpenAI

        base_url = os.getenv("OPENAI_BASE_URL")  # allow custom endpoints
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            response_format={"type": "json_object"},
            timeout=15,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        # Validate the extracted intent against the allowlist
        if parsed.get("intent") not in SUPPORTED_INTENTS:
            logger.warning(
                "LLM returned unsupported intent %r — falling back.",
                parsed.get("intent"),
            )
            return interpret_question(question), "rule-based fallback (invalid AI intent)"

        # Validate month parameters for month_comparison
        if parsed["intent"] == "month_comparison":
            for key in ("month1", "month2"):
                value = str(parsed.get(key, ""))
                if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", value):
                    logger.warning(
                        "LLM returned invalid month %r — falling back.", value,
                    )
                    return (
                        interpret_question(question),
                        "rule-based fallback (invalid AI month format)",
                    )

        return parsed, "LLM intent extraction"

    except json.JSONDecodeError as exc:
        logger.warning("LLM returned invalid JSON: %s — falling back.", exc)
        return interpret_question(question), "rule-based fallback (invalid AI JSON)"

    except Exception as exc:
        # Catch network errors, timeouts, auth failures, etc.
        logger.warning("LLM API error: %s — falling back.", exc)
        return interpret_question(question), "rule-based fallback (AI API error)"
