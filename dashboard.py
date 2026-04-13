import streamlit as st
from datetime import datetime

from analysis import load_portfolio_extended

from views import (
    overview,
    gold_silver,
    portfolio,
    holdings as holdings_page,
    scanner,
    news,
    goals,
    budget,
    learn,
    manage,
    predictions,
)


# --- Config ---

st.set_page_config(
    page_title="Finance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown(
    """
<style>
    /* Tighter spacing */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }

    /* Card-like containers */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border: 1px solid #3d3d5c;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    div[data-testid="stMetric"] label {
        font-size: 0.85rem !important;
        color: #a0a0b8 !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
    }

    /* Section headers */
    h2 {
        border-bottom: 2px solid #4a4a6a;
        padding-bottom: 0.4rem;
        margin-top: 1.5rem !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }

    /* Expanders */
    details {
        border: 1px solid #3d3d5c !important;
        border-radius: 10px !important;
        margin-bottom: 0.5rem;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        font-weight: 600 !important;
    }

    /* Alert boxes */
    .stAlert { border-radius: 8px; }

    /* Hide default footer */
    footer { visibility: hidden; }
</style>
""",
    unsafe_allow_html=True,
)


# --- Sidebar Navigation ---
st.sidebar.title("📊 Finance Dashboard")
st.sidebar.caption(f"📅 {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    [
        "🏠 Overview",
        "───── Markets ─────",
        "🪙 Gold & Silver",
        "🔎 Market Scanner",
        "📰 News",
        "───── My Money ─────",
        "📁 My Portfolio",
        "🔬 Holdings Analysis",
        "🎯 Goals",
        "💰 Budget",
        "───── Tools ─────",
        "� Prediction Scorecard",
        "�📚 Learn",
        "⚙️ Manage Portfolio",
    ],
    label_visibility="collapsed",
)

# Skip separator items
if page.startswith("─"):
    page = "🏠 Overview"


# Load data once
@st.cache_data(ttl=60)
def load_holdings():
    return load_portfolio_extended()


holdings = load_holdings()


# --- Page Router ---
PAGE_MAP = {
    "🏠 Overview": overview.render,
    "🪙 Gold & Silver": gold_silver.render,
    "📁 My Portfolio": portfolio.render,
    "🔬 Holdings Analysis": holdings_page.render,
    "🔎 Market Scanner": scanner.render,
    "📰 News": news.render,
    "🎯 Goals": goals.render,
    "💰 Budget": budget.render,
    "� Prediction Scorecard": predictions.render,
    "�📚 Learn": learn.render,
    "⚙️ Manage Portfolio": manage.render,
}

render_fn = PAGE_MAP.get(page)
if render_fn:
    render_fn(holdings)


# --- Sidebar Footer ---
st.sidebar.divider()
st.sidebar.caption("Data: Yahoo Finance, AMFI India, Google News")
st.sidebar.caption("Built with Streamlit")
