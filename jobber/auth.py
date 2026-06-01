"""Optional password gate — active only when JOBBER_PASSWORD is set (e.g. when shared online)."""
from __future__ import annotations

import hmac

import streamlit as st

from . import config


def require_auth() -> None:
    # Gate is on when serving online (serve_online.ps1 flag) or hosted in the cloud.
    if not (config.env("JOBBER_REQUIRE_PASSWORD") or config.is_cloud()):
        return  # local use → no gate
    password = config.env("JOBBER_PASSWORD")
    if not password:
        st.error("This online deployment needs a password. "
                 "Add **JOBBER_PASSWORD** to the app's secrets and reboot.")
        st.stop()
    if st.session_state.get("_authed"):
        return

    st.title("🎯 Jobber")
    st.caption("Enter your access password to continue.")
    with st.form("jobber_login"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")
    if submitted:
        if hmac.compare_digest(entered or "", password):
            st.session_state["_authed"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()
