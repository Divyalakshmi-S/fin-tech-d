"""
Streamlit authentication UI using Supabase Auth.

Renders login/signup forms and manages session state.
When DB is not configured, allows guest access with local JSON fallback.
"""

import streamlit as st
import db


def _init_session():
    """Ensure session state keys exist."""
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "user_email" not in st.session_state:
        st.session_state.user_email = None


def get_user_id():
    """Return the current user's UUID, or None if not logged in."""
    _init_session()
    return st.session_state.user_id


def is_logged_in():
    """Check if the user is authenticated."""
    _init_session()
    return st.session_state.user_id is not None


def logout():
    """Clear session and sign out."""
    db.sign_out()
    st.session_state.auth_token = None
    st.session_state.user_id = None
    st.session_state.user_email = None


def render_auth_page():
    """Render login/signup page. Returns True if user is authenticated."""
    _init_session()

    # If DB isn't configured, skip auth (local dev / bot mode)
    if not db.is_db_available():
        st.session_state.user_id = None
        st.session_state.user_email = "local"
        return True

    # Already logged in — validate token
    if st.session_state.auth_token:
        user = db.get_user_from_session(st.session_state.auth_token)
        if user:
            st.session_state.user_id = user.id
            st.session_state.user_email = user.email
            return True
        else:
            # Token expired
            logout()

    # --- Auth UI ---
    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0 1rem 0;">
            <h1>📊 Finance Dashboard</h1>
            <p style="color: #888;">Sign in to access your personal portfolio & analysis</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_login, tab_signup = st.tabs(["🔑 Login", "📝 Sign Up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pwd")
            submitted = st.form_submit_button("Login", use_container_width=True)

            if submitted:
                if not email or not password:
                    st.error("Please enter email and password")
                else:
                    session, error = db.sign_in(email, password)
                    if session:
                        st.session_state.auth_token = session.access_token
                        st.session_state.user_id = session.user.id
                        st.session_state.user_email = session.user.email
                        st.rerun()
                    else:
                        st.error(f"Login failed: {error}")

    with tab_signup:
        with st.form("signup_form"):
            new_email = st.text_input("Email", key="signup_email")
            new_password = st.text_input(
                "Password",
                type="password",
                key="signup_pwd",
                help="Minimum 6 characters",
            )
            confirm_password = st.text_input(
                "Confirm Password", type="password", key="signup_confirm"
            )
            signed_up = st.form_submit_button(
                "Create Account", use_container_width=True
            )

            if signed_up:
                if not new_email or not new_password:
                    st.error("Please fill in all fields")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters")
                elif new_password != confirm_password:
                    st.error("Passwords do not match")
                else:
                    user, error = db.sign_up(new_email, new_password)
                    if user:
                        st.success(
                            "Account created! Please check your email to confirm, then log in."
                        )
                    else:
                        st.error(f"Sign-up failed: {error}")

    return False


def render_sidebar_user():
    """Show user info and logout button in the sidebar."""
    _init_session()
    if st.session_state.user_email and st.session_state.user_email != "local":
        st.sidebar.markdown(f"👤 **{st.session_state.user_email}**")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()
