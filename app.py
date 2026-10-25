"""Streamlit user interface for the Mini AI Business Intelligence Assistant.

The FastAPI backend (``main.py``) remains the authoritative source of all
analytics answers.  This module provides a polished, responsive UI that
communicates with the API over HTTP.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Mini AI BI Assistant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS for a polished look
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* Header gradient */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 700;
    }
    .main-header p {
        margin: 0.3rem 0 0 0;
        font-size: 0.95rem;
        opacity: 0.9;
    }

    /* Metric cards */
    .metric-card {
        background: #f8f9fa;
        border-left: 4px solid #667eea;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
    }
    .metric-card h3 {
        margin: 0;
        font-size: 0.85rem;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-card .value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #212529;
        margin: 0.2rem 0;
    }

    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 50px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-ok {
        background: #d4edda;
        color: #155724;
    }
    .status-warn {
        background: #fff3cd;
        color: #856404;
    }
    .status-error {
        background: #f8d7da;
        color: #721c24;
    }

    /* Intent tag */
    .intent-tag {
        display: inline-block;
        background: #e8eaf6;
        color: #283593;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    .method-tag {
        display: inline-block;
        background: #e0f2f1;
        color: #00695c;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    /* Hide the default Streamlit footer */
    footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

EXAMPLE_QUESTIONS = [
    "What is the total revenue?",
    "Which product generated the highest revenue?",
    "What is the monthly revenue trend?",
    "Which region generated the highest sales?",
    "Compare January 2026 and February 2026 revenue.",
    "What is the revenue by category?",
    "Compare online vs retail sales channel revenue.",
    "Show me data quality summary.",
]

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="main-header">
        <h1>📊 Mini AI Business Intelligence Assistant</h1>
        <p>Ask natural-language questions about sales transactions.
        Answers are computed from the database — the AI only interprets your intent.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image(
        "https://img.icons8.com/color/96/combo-chart--v1.png",
        width=64,
    )
    st.subheader("💡 Try an example")
    for example in EXAMPLE_QUESTIONS:
        if st.button(example, use_container_width=True, key=f"ex_{example}"):
            st.session_state["question"] = example

    st.markdown("---")

    # API connection status
    st.subheader("🔗 Connection Status")
    try:
        health = requests.get(f"{API_URL}/health", timeout=5).json()
        st.markdown(
            '<span class="status-badge status-ok">● API Connected</span>',
            unsafe_allow_html=True,
        )
        dq = health.get("data_quality", {})
        ingest = health.get("ingestion_summary", {})

        if dq:
            st.caption(
                f"📦 {dq.get('total_rows', '?')} records · "
                f"✅ {dq.get('valid_revenue_rows', '?')} valid · "
                f"⚠️ {dq.get('flagged_rows', '?')} flagged · "
                f"↩️ {dq.get('returned_rows_excluded', '?')} returned"
            )
        if ingest.get("date_range"):
            st.caption(f"📅 {ingest['date_range']}")
    except requests.RequestException:
        st.markdown(
            '<span class="status-badge status-error">● API Offline</span>',
            unsafe_allow_html=True,
        )
        st.error("Start the backend:\n```\nuvicorn main:app --reload\n```")
        health = None

    st.markdown("---")
    st.subheader("📐 Revenue Definition")
    st.markdown(
        "**Net revenue** = quantity × unit price − discount  \n"
        "Only **Completed** transactions with valid positive "
        "quantities, positive unit prices, and valid discounts "
        "are included. Returned transactions are excluded."
    )

    st.markdown("---")
    st.caption("Built for the RSG Graduate Engineer Trainee Challenge")


# ---------------------------------------------------------------------------
# Question input
# ---------------------------------------------------------------------------

col_q, col_b = st.columns([5, 1])
with col_q:
    question = st.text_input(
        "🔍 Ask a sales question",
        key="question",
        placeholder="e.g. Which region generated the highest sales?",
        label_visibility="visible",
    )
with col_b:
    st.write("")  # spacer for alignment
    st.write("")
    analyze_clicked = st.button("🚀 Analyze", type="primary", use_container_width=True)


# ---------------------------------------------------------------------------
# Answer display
# ---------------------------------------------------------------------------

def _render_chart(result: dict):
    """Render a Plotly chart appropriate to the intent."""
    intent = result.get("intent")
    data = result.get("supporting_data", [])
    if not data:
        return

    if intent == "monthly_trend":
        df = pd.DataFrame(data)
        fig = px.area(
            df, x="month", y="revenue",
            markers=True,
            title="Monthly Net Revenue Trend",
            labels={"month": "Month", "revenue": "Revenue (₹)"},
            color_discrete_sequence=["#667eea"],
        )
        fig.update_layout(
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    elif intent == "top_product":
        df = pd.DataFrame(data)
        fig = px.bar(
            df, x="product", y="revenue",
            title="Revenue by Product",
            labels={"product": "Product", "revenue": "Revenue (₹)"},
            color="revenue",
            color_continuous_scale="Viridis",
        )
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    elif intent == "top_region":
        df = pd.DataFrame(data)
        fig = px.bar(
            df, x="region", y="revenue",
            title="Revenue by Region",
            labels={"region": "Region", "revenue": "Revenue (₹)"},
            color="revenue",
            color_continuous_scale="Tealgrn",
        )
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    elif intent == "month_comparison":
        # Filter to only month rows (exclude the change summary row)
        month_rows = [r for r in data if "month" in r and "revenue" in r]
        if month_rows:
            df = pd.DataFrame(month_rows)
            fig = px.bar(
                df, x="month", y="revenue",
                title="Month-over-Month Revenue Comparison",
                labels={"month": "Month", "revenue": "Revenue (₹)"},
                color="month",
                color_discrete_sequence=["#667eea", "#764ba2"],
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

    elif intent == "revenue_by_category":
        df = pd.DataFrame(data)
        fig = px.pie(
            df, names="category", values="revenue",
            title="Revenue Distribution by Category",
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.4,
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    elif intent == "sales_channel_comparison":
        df = pd.DataFrame(data)
        fig = px.bar(
            df, x="sales_channel", y="revenue",
            title="Revenue by Sales Channel",
            labels={"sales_channel": "Channel", "revenue": "Revenue (₹)"},
            color="sales_channel",
            color_discrete_sequence=["#667eea", "#764ba2"],
        )
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


if analyze_clicked and question and question.strip():
    try:
        with st.spinner("🔄 Analyzing sales data..."):
            response = requests.post(
                f"{API_URL}/ask",
                json={"question": question},
                timeout=30,
            )

        if response.status_code >= 400:
            detail = response.json().get("detail", response.text) if response.headers.get(
                "content-type", ""
            ).startswith("application/json") else response.text
            st.error(f"❌ Request failed ({response.status_code}): {detail}")
        else:
            result = response.json()

            # Answer
            if result.get("ok"):
                st.success(f"**{result['answer']}**")
            else:
                st.warning(f"⚠️ {result['answer']}")

            # Metadata tags
            st.markdown(
                f'<span class="intent-tag">Intent: {result.get("intent", "?")}</span>'
                f'<span class="method-tag">Method: {result.get("interpretation_method", "?")}</span>',
                unsafe_allow_html=True,
            )

            # How was this calculated?
            with st.expander("📐 How was this calculated?", expanded=False):
                st.write(result.get("sql_description", ""))

            # Chart
            _render_chart(result)

            # Supporting data table
            data = result.get("supporting_data", [])
            if data:
                with st.expander("📋 Supporting Data", expanded=True):
                    st.dataframe(
                        pd.DataFrame(data),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.info("No supporting data rows for this query.")

    except requests.ConnectionError:
        st.error(
            "❌ Cannot connect to the API. Start the backend first:\n\n"
            "```bash\nuvicorn main:app --reload\n```"
        )
    except requests.Timeout:
        st.error("⏰ The request timed out. Please try again.")
    except requests.RequestException as exc:
        st.error(f"❌ Request error: {exc}")

# ---------------------------------------------------------------------------
# Dashboard section (only when API is available)
# ---------------------------------------------------------------------------

if health and health.get("status") == "ok":
    st.markdown("---")
    st.subheader("📈 Quick Dashboard")
    st.caption("Overview metrics from the loaded dataset (refreshed on page load)")

    # Fetch dashboard data from the API
    dashboard_data = {}
    for intent_name in ["total_revenue", "top_product", "monthly_trend", "top_region", "revenue_by_category"]:
        try:
            r = requests.post(
                f"{API_URL}/ask",
                json={"question": f"_dashboard_{intent_name}"},
                timeout=10,
            )
            # The question might not match — use specific phrasing
        except requests.RequestException:
            pass

    # Use specific questions that the parser will understand
    try:
        rev_resp = requests.post(
            f"{API_URL}/ask",
            json={"question": "What is the total revenue?"},
            timeout=10,
        ).json()
        prod_resp = requests.post(
            f"{API_URL}/ask",
            json={"question": "Which product generated the highest revenue?"},
            timeout=10,
        ).json()
        region_resp = requests.post(
            f"{API_URL}/ask",
            json={"question": "Which region generated the highest sales?"},
            timeout=10,
        ).json()
        trend_resp = requests.post(
            f"{API_URL}/ask",
            json={"question": "What is the monthly revenue trend?"},
            timeout=10,
        ).json()

        # KPI row
        dq = health.get("data_quality", {})
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        total_rev = rev_resp.get("supporting_data", [{}])[0].get("total_revenue", 0) if rev_resp.get("ok") else 0
        total_txn = rev_resp.get("supporting_data", [{}])[0].get("transaction_count", 0) if rev_resp.get("ok") else 0
        total_units = rev_resp.get("supporting_data", [{}])[0].get("total_units_sold", 0) if rev_resp.get("ok") else 0
        top_prod_name = prod_resp.get("supporting_data", [{}])[0].get("product", "N/A") if prod_resp.get("ok") and prod_resp.get("supporting_data") else "N/A"

        with kpi1:
            st.metric("💰 Total Revenue", f"₹{total_rev:,.2f}")
        with kpi2:
            st.metric("📦 Transactions", f"{total_txn:,}")
        with kpi3:
            st.metric("📊 Units Sold", f"{total_units:,}")
        with kpi4:
            st.metric("🏆 Top Product", top_prod_name)

        # Charts row
        chart1, chart2 = st.columns(2)

        with chart1:
            if trend_resp.get("ok") and trend_resp.get("supporting_data"):
                trend_df = pd.DataFrame(trend_resp["supporting_data"])
                fig = px.area(
                    trend_df, x="month", y="revenue",
                    markers=True,
                    title="Monthly Revenue Trend",
                    labels={"month": "Month", "revenue": "Revenue (₹)"},
                    color_discrete_sequence=["#667eea"],
                )
                fig.update_layout(
                    height=350,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)

        with chart2:
            if region_resp.get("ok") and region_resp.get("supporting_data"):
                region_df = pd.DataFrame(region_resp["supporting_data"])
                fig = px.bar(
                    region_df, x="region", y="revenue",
                    title="Revenue by Region",
                    labels={"region": "Region", "revenue": "Revenue (₹)"},
                    color="revenue",
                    color_continuous_scale="Tealgrn",
                )
                fig.update_layout(
                    height=350,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)

        # Product breakdown
        if prod_resp.get("ok") and prod_resp.get("supporting_data"):
            st.subheader("🏷️ Product Revenue Breakdown")
            prod_df = pd.DataFrame(prod_resp["supporting_data"])
            fig = px.bar(
                prod_df, x="product", y="revenue",
                title="Revenue by Product",
                labels={"product": "Product", "revenue": "Revenue (₹)"},
                color="revenue",
                color_continuous_scale="Viridis",
            )
            fig.update_layout(
                height=350,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    except requests.RequestException:
        st.warning("Could not load dashboard data. Ensure the API is running.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #6c757d; font-size: 0.85rem;">
        <strong>Mini AI BI Assistant</strong> · RSG Graduate Engineer Trainee Challenge<br>
        🔒 The LLM is never allowed to generate or execute SQL.
        Only predefined, read-only analytics queries are supported.
    </div>
    """,
    unsafe_allow_html=True,
)
