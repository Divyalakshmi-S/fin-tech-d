import streamlit as st
from datetime import datetime

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv not required on Streamlit Cloud

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass  # truststore not required; needed when behind SSL-intercepting proxies

from analysis import load_portfolio_extended
import auth
import db

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
    calculators,
    tax_planning,
    financial_health,
    checkup,
    family,
)
from ui_helpers import render_disclaimer


# --- Config ---

st.set_page_config(
    page_title="Finance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---

# Theme toggle
if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"

if st.session_state["theme"] == "light":
    _bg = "#f5f5f5"
    _card_bg = "linear-gradient(135deg, #ffffff 0%, #f0f0f5 100%)"
    _card_border = "#d0d0e0"
    _text_muted = "#606080"
    _sidebar_bg = "linear-gradient(180deg, #e8e8f0 0%, #dde4f0 100%)"
    _section_border = "#b0b0d0"
    _shadow = "rgba(0,0,0,0.05)"
else:
    _bg = ""  # use Streamlit default dark
    _card_bg = "linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%)"
    _card_border = "#3d3d5c"
    _text_muted = "#a0a0b8"
    _sidebar_bg = "linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)"
    _section_border = "#4a4a6a"
    _shadow = "rgba(0,0,0,0.15)"

st.markdown(
    f"""
<style>
    /* Tighter spacing */
    .block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}

    /* Card-like containers */
    div[data-testid="stMetric"] {{
        background: {_card_bg};
        border: 1px solid {_card_border};
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 8px {_shadow};
    }}
    div[data-testid="stMetric"] label {{
        font-size: 0.85rem !important;
        color: {_text_muted} !important;
    }}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
        font-size: 1.4rem !important;
        font-weight: 700 !important;
    }}

    /* Section headers */
    h2 {{
        border-bottom: 2px solid {_section_border};
        padding-bottom: 0.4rem;
        margin-top: 1.5rem !important;
    }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background: {_sidebar_bg};
    }}

    /* Expanders */
    details {{
        border: 1px solid {_card_border} !important;
        border-radius: 10px !important;
        margin-bottom: 0.5rem;
    }}

    /* Tabs */
    button[data-baseweb="tab"] {{
        font-weight: 600 !important;
    }}

    /* Alert boxes */
    .stAlert {{ border-radius: 8px; }}

    /* Hide default footer */
    footer {{ visibility: hidden; }}
</style>
""",
    unsafe_allow_html=True,
)

# --- Authentication Gate ---
if not auth.render_auth_page():
    st.stop()

user_id = auth.get_user_id()


# --- Sidebar Navigation ---
st.sidebar.title("📊 Finance Dashboard")
auth.render_sidebar_user()
st.sidebar.caption(f"📅 {datetime.now().strftime('%d %b %Y, %I:%M %p')}")

# Theme toggle
current_theme = st.session_state.get("theme", "dark")
theme_label = "🌙 Dark" if current_theme == "dark" else "☀️ Light"
if st.sidebar.button(f"Theme: {theme_label}"):
    st.session_state["theme"] = "light" if current_theme == "dark" else "dark"
    st.rerun()

st.sidebar.divider()

# Data refresh
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(f"⏱️ Data cached for 5 min")

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
        "───── Planning ─────",
        "📋 Tax Planning",
        "🧮 Calculators",
        "👨‍👩‍👧‍👦 Family",
        "🛡️ Financial Health",
        "🏥 Health Checkup",
        "───── Tools ─────",
        "📈 Prediction Scorecard",
        "📚 Learn",
        "⚙️ Manage Portfolio",
    ],
    label_visibility="collapsed",
)

# Skip separator items
if page.startswith("─"):
    page = "🏠 Overview"


# Load data once
@st.cache_data(ttl=60)
def load_holdings(_user_id):
    if db.is_db_available() and _user_id:
        portfolio_rows = db.load_portfolio(_user_id)
        return load_portfolio_extended(from_rows=portfolio_rows)
    # Use user-scoped JSON path for offline fallback
    user_path = db._json_path("portfolio.json", user_id=_user_id)
    return load_portfolio_extended(path=user_path)


holdings = load_holdings(user_id)

# --- New user welcome banner ---
if not holdings and page == "🏠 Overview":
    st.info(
        "👋 **Welcome!** You haven't added any holdings yet. "
        "Head to **⚙️ Manage Portfolio** in the sidebar to add your stocks and mutual funds."
    )


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
    "📋 Tax Planning": tax_planning.render,
    "🧮 Calculators": calculators.render,
    "👨‍👩‍👧‍👦 Family": family.render,
    "🛡️ Financial Health": financial_health.render,
    "🏥 Health Checkup": checkup.render,
    "📈 Prediction Scorecard": predictions.render,
    "📚 Learn": learn.render,
    "⚙️ Manage Portfolio": manage.render,
}

render_fn = PAGE_MAP.get(page)
if render_fn:
    render_fn(holdings)

# Compliance disclaimer on every page
render_disclaimer()


# --- Sidebar Footer ---
st.sidebar.divider()
st.sidebar.caption("Data: Yahoo Finance, AMFI India, Google News")
st.sidebar.caption("Built with Streamlit")
