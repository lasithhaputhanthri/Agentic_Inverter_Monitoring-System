"""Operator dashboard for solar inverter fleet incident monitoring and response.

Purpose: Streamlit operator interface satisfying Rule 28 and Rule 50:
         - Isolated frontend connecting ONLY via authenticated HTTP to the FastAPI backend.
         - ZERO imports of simulator, faults, executor, or storage.
         - Reads API key from IIR_API_KEY environment variable.
         - Renders model justifications strictly as plain text (no HTML).
         - Displays Approve and Reject action buttons ONLY for the approver role.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/v1")
API_KEY = os.getenv("IIR_API_KEY", "")


def get_headers() -> dict[str, str]:
    """Construct HTTP request headers including API key."""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    return headers


def fetch_api(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Perform authenticated GET request to the API."""
    url = f"{API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=10)
        if response.status_code == 401:
            st.error("Authentication failed: invalid or missing API key.")
            return None
        if response.status_code == 403:
            st.error("Permission denied: insufficient role privileges.")
            return None
        if not response.ok:
            st.error(f"API Error ({response.status_code}): {response.text}")
            return None
        return response.json()
    except Exception as e:
        st.error(f"Failed to connect to API at {url}: {e}")
        return None


def post_decision(proposal_id: str, decision: str, reason: str = "") -> bool:
    """Submit operator proposal decision (approve/reject)."""
    url = f"{API_BASE_URL.rstrip('/')}/proposals/{proposal_id}/decision"
    payload = {"decision": decision, "reason": reason if reason else None}
    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        if response.status_code == 409:
            st.warning(f"Proposal {proposal_id} was already decided.")
            return False
        if not response.ok:
            st.error(f"Decision failed ({response.status_code}): {response.text}")
            return False
        st.success(f"Proposal {proposal_id} successfully {decision}d!")
        return True
    except Exception as e:
        st.error(f"Error submitting decision: {e}")
        return False


def get_current_user_role() -> str:
    """Determine current authenticated role via API or environment fallback."""
    env_role = os.getenv("IIR_ROLE")
    if env_role:
        return env_role.lower()

    user_info = fetch_api("auth/me")
    if user_info and isinstance(user_info, dict):
        return str(user_info.get("role", "viewer")).lower()
    return "viewer"


def main() -> None:
    st.set_page_config(
        page_title="Inverter Incident Response Dashboard",
        page_icon="⚡",
        layout="wide",
    )

    st.title("⚡ Solar Fleet Incident Response Monitor")

    # API Connection and authentication banner
    if not API_KEY:
        st.warning(
            "⚠️ No API key set in IIR_API_KEY environment variable. Operations will fail authentication."
        )

    role = get_current_user_role()
    st.sidebar.markdown(f"**Current Role:** `{role}`")
    st.sidebar.markdown(f"**API Endpoint:** `{API_BASE_URL}`")

    # Navigation tabs
    tab_fleet, tab_alerts, tab_proposals, tab_timeline, tab_usage = st.tabs(
        ["Fleet Status", "Alerts", "Remediation Proposals", "Incident Timeline", "Usage & Quota"]
    )

    # 1. Fleet Status View
    with tab_fleet:
        st.header("Fleet Overview (20 Inverters)")
        if st.button("Refresh Fleet", key="btn_refresh_fleet"):
            pass
        fleet_data = fetch_api("fleet/status")
        if fleet_data and "devices" in fleet_data:
            devices = fleet_data["devices"]
            cols = st.columns(4)
            for idx, dev in enumerate(devices):
                col = cols[idx % 4]
                status_color: Literal["normal", "inverse", "off"] = (
                    "normal" if dev["status"] == "nominal" else "inverse"
                )
                with col:
                    st.metric(
                        label=dev["device_id"],
                        value=f"{dev['ac_power_w']:.1f} W",
                        delta=f"Temp: {dev['temperature_c']:.1f} °C | Status: {dev['status']}",
                        delta_color=status_color,
                    )
                    st.caption(
                        f"Grid: {dev['grid_voltage_v']:.1f}V | DC: {dev['dc_voltage_v']:.1f}V | Relay: {dev['relay_state']}"
                    )
        else:
            st.info("No fleet telemetry available.")

    # 2. Alerts View
    with tab_alerts:
        st.header("Active & Historical Alerts")
        dev_filter = st.text_input("Filter by Device ID (e.g. INV-01)", key="alert_dev_filter")
        params = {}
        if dev_filter:
            params["device_id"] = dev_filter.strip()

        alerts_data = fetch_api("alerts", params=params)
        if alerts_data and "items" in alerts_data:
            items = alerts_data["items"]
            if not items:
                st.info("No alerts found matching criteria.")
            for alert in items:
                with st.expander(
                    f"[{alert['severity'].upper()}] {alert['device_id']} - {alert['rule']} ({alert['ts']})"
                ):
                    st.write(f"**Message:** {alert['message']}")
                    st.write(
                        f"**Observed:** `{alert['observed']}` | **Threshold:** `{alert['threshold']}`"
                    )
                    st.write(f"**Alert ID:** `{alert['alert_id']}`")
        else:
            st.info("No alert records retrieved.")

    # 3. Remediation Proposals View
    with tab_proposals:
        st.header("Pending Remediation Proposals")
        proposals_data = fetch_api("proposals", params={"status": "pending"})
        if proposals_data and isinstance(proposals_data, list):
            if not proposals_data:
                st.info("No pending proposals awaiting decision.")
            for prop in proposals_data:
                st.subheader(f"Proposal for {prop['device_id']}: Action `{prop['action']}`")
                st.text("Model Justification (Plain Text):")
                # SEC-50: Strictly plain text, never HTML
                st.code(prop["justification"], language=None)
                st.caption(
                    f"Proposal ID: {prop['proposal_id']} | Diagnosis ID: {prop['diagnosis_id']}"
                )

                # Rule 50: Action buttons visible ONLY for approver role
                if role == "approver":
                    reason_input = st.text_input(
                        "Review Note / Reason (Optional):",
                        key=f"reason_{prop['proposal_id']}",
                        max_chars=4000,
                    )
                    btn_col1, btn_col2, _ = st.columns([1, 1, 4])
                    with btn_col1:
                        if st.button("Approve", key=f"app_{prop['proposal_id']}"):
                            post_decision(prop["proposal_id"], "approve", reason_input)
                    with btn_col2:
                        if st.button("Reject", key=f"rej_{prop['proposal_id']}"):
                            post_decision(prop["proposal_id"], "reject", reason_input)
                else:
                    st.info("🔒 Decision actions disabled: requires 'approver' role.")
                st.divider()
        else:
            st.info("No pending proposals.")

    # 4. Incident Timeline View
    with tab_timeline:
        st.header("Chronological Incident Timeline")
        run_id_filter = st.text_input("Filter by Run ID (optional):", key="timeline_run_filter")
        t_params = {}
        if run_id_filter:
            t_params["run_id"] = run_id_filter.strip()
        timeline_data = fetch_api("timeline", params=t_params)
        if timeline_data and isinstance(timeline_data, list):
            if not timeline_data:
                st.info("No timeline events found.")
            for event in timeline_data:
                st.text(f"[{event['timestamp']}] [{event['type'].upper()}] {event['summary']}")
        else:
            st.info("No timeline events.")

    # 5. Usage & Quotas View
    with tab_usage:
        st.header("Daily Platform Usage & Limits")
        usage_data = fetch_api("usage")
        if usage_data:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric(
                    "Requests Today",
                    f"{usage_data['request_count']} / {usage_data['daily_request_limit']}",
                )
            with c2:
                st.metric(
                    "LLM Inferences",
                    f"{usage_data['llm_call_count']} / {usage_data['daily_llm_limit']}",
                )
            with c3:
                st.metric(
                    "Tokens Consumed",
                    f"{usage_data['tokens_used']} / {usage_data['daily_token_limit']}",
                )


if __name__ == "__main__":
    main()
