"""
Authentication module — thin wrapper around Streamlit's built-in auth.

On Streamlit Cloud: uses st.login() / st.user for Google/GitHub SSO.
Locally (no auth configured): auto-enters guest mode with local JSON storage.

All views call auth.get_user_id() — returns the user's email as their ID
(used to key data in Supabase), or None for guest mode.
"""

import streamlit as st


def get_user_id():
    """Return the current user's email (used as DB key), or None for guest."""
    user = st.user
    if user and user.get("is_logged_in"):
        return user.get("email")
    if st.session_state.get("_guest_mode"):
        return None
    return None


def is_logged_in():
    """Check if the user is authenticated or in guest mode."""
    user = st.user
    if user and user.get("is_logged_in"):
        return True
    return st.session_state.get("_guest_mode", False)


def render_auth_page():
    """Gate the app behind auth. Returns True if user can proceed."""
    user = st.user

    # Already logged in via Streamlit auth
    if user and user.get("is_logged_in"):
        return True

    # Already in guest mode
    if st.session_state.get("_guest_mode"):
        return True

    # --- Show login page ---
    st.markdown(
        """
        <style>
            /* Hide sidebar and header on login page */
            section[data-testid="stSidebar"] { display: none; }
            header[data-testid="stHeader"] { display: none; }
            footer { display: none; }

            .block-container {
                padding: 0 !important;
                max-width: 480px !important;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
            }

            .login-card {
                background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
                border: 1px solid #3d3d5c;
                border-radius: 20px;
                padding: 2rem 2rem 1rem;
                width: 100%;
                max-width: 400px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                text-align: center;
                margin: auto;
                margin-bottom: 1.5rem;
            }
            @media (prefers-color-scheme: light) {
                .login-card {
                    background: linear-gradient(135deg, #ffffff 0%, #f0f0f5 100%);
                    border: 1px solid #d0d0e0;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.08);
                }
                .login-card .subtitle { color: #606080 !important; }
                .login-card .features span { color: #606080 !important; }
            }
            .login-card .logo { font-size: 3rem; margin-bottom: 0.3rem; }
            .login-card h1 {
                font-size: 1.6rem;
                font-weight: 700;
                margin: 0 0 0.2rem 0;
                border: none !important;
                padding: 0 !important;
            }
            .login-card .subtitle {
                color: #a0a0b8;
                font-size: 0.9rem;
                margin-bottom: 1rem;
            }
            .login-card .features {
                display: flex;
                justify-content: center;
                gap: 1rem;
                margin-bottom: 0.5rem;
                flex-wrap: wrap;
            }
            .login-card .features span {
                font-size: 0.78rem;
                color: #a0a0b8;
            }
        </style>

        <div class="login-card">
            <div class="logo">📊</div>
            <h1>Finance Dashboard</h1>
            <p class="subtitle">Track your portfolio, plan your future</p>
            <div class="features">
                <span>📁 Portfolio</span>
                <span>🪙 Gold & Silver</span>
                <span>🎯 Goals</span>
                <span>📋 Tax</span>
                <span>🏦 Retirement</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("🔑  Sign in with Google", use_container_width=True, type="primary"):
        st.login("google")
    if st.button("👤  Continue as Guest", use_container_width=True):
        st.session_state["_guest_mode"] = True
        st.rerun()

    return False


def render_sidebar_user():
    """Show user info and logout button in the sidebar."""
    user = st.user
    if user and user.get("is_logged_in"):
        email = user.get("email", "")
        name = user.get("name", email)
        st.sidebar.markdown(f"👤 **{name}**")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            st.logout()
            st.rerun()
    elif st.session_state.get("_guest_mode"):
        st.sidebar.markdown("👤 **Guest**")
        st.sidebar.caption("Data saved locally only")
