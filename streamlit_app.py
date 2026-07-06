"""
Streamlit UI for SubstanceGuard. Talks to the FastAPI backend over HTTP (API_BASE_URL,
defaulting to http://localhost:8000 for local dev, http://api:8000 inside docker-compose)
rather than importing the pipeline directly -- the pipeline uses a SQLite-backed
LangGraph checkpointer for genuine human-in-the-loop pause/resume, which only makes
sense as shared state behind one backend process, not duplicated into a Streamlit
script-rerun process.
"""
import os
import time

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="SubstanceGuard", page_icon="\U0001f9ea", layout="wide")

# On Streamlit Community Cloud, API_BASE_URL (the deployed FastAPI URL, e.g. a Render
# service) comes from the app's Secrets UI (st.secrets), not a local .env file.
try:
    _secrets = dict(st.secrets)
except FileNotFoundError:
    _secrets = {}  # no secrets.toml at all (local dev relying on .env/os.environ) -- expected

API_BASE_URL = _secrets.get("API_BASE_URL", os.environ.get("API_BASE_URL", "http://localhost:8000"))

STATUS_COLORS = {
    "COMPLIANT": "green", "NON_COMPLIANT": "red", "NEEDS_REVIEW": "orange",
    "processing": "gray", "complete": "green", "needs_review": "orange", "error": "red",
}


def _badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "gray")
    return f":{color}[**{status}**]"


st.title("\U0001f9ea SubstanceGuard")
st.caption(
    "AI-assisted REACH / RoHS / draft-PFAS compliance screening for supplier SDS and test "
    "reports. Every verdict below is a **screening result for review**, citing the exact "
    "regulation, article/annex and threshold checked -- not a legal determination."
)

tab_screen, tab_queue = st.tabs(["\U0001f4c4 Screen a Document", "\U0001f6a9 Review Queue"])

with tab_screen:
    uploaded = st.file_uploader("Upload a supplier SDS / test report (PDF)", type=["pdf"])
    if uploaded is not None and st.button("Screen document", type="primary"):
        with st.spinner("Submitting to SubstanceGuard..."):
            resp = requests.post(
                f"{API_BASE_URL}/screen",
                files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
                timeout=30,
            )
        if resp.status_code != 202:
            st.error(f"Upload failed ({resp.status_code}): {resp.text}")
        else:
            st.session_state["product_id"] = resp.json()["product_id"]
            st.session_state["polling"] = True

    product_id = st.session_state.get("product_id")
    if product_id:
        st.write(f"**Product ID:** `{product_id}`")
        status_placeholder = st.empty()
        report = None
        status = "processing"

        if st.session_state.get("polling"):
            with st.spinner("Running pipeline (extraction -> graph lookup -> RAG -> verdict)..."):
                for _ in range(60):
                    r = requests.get(f"{API_BASE_URL}/product/{product_id}/status", timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        status = data["status"]
                        report = data.get("report")
                        if status in ("complete", "needs_review", "error"):
                            break
                    time.sleep(1)
            st.session_state["polling"] = False
        else:
            r = requests.get(f"{API_BASE_URL}/product/{product_id}/status", timeout=10)
            if r.status_code == 200:
                data = r.json()
                status = data["status"]
                report = data.get("report")

        status_placeholder.markdown(f"**Status:** {_badge(status)}")

        if report:
            st.subheader(f"Compliance Report: {report['product_name']}")
            st.markdown(f"**Overall status:** {_badge(report['overall_status'])}")

            rows = []
            for v in report["substance_verdicts"]:
                rows.append({
                    "Substance": v["substance_name"],
                    "CAS": v["cas_number"] or "(none extracted)",
                    "Component": v["component_name"],
                    "Measured": f"{v['measured_value']} {v['measured_unit']}",
                    "Regulation": v["regulation_name"] or "-",
                    "Threshold": f"{v['threshold_value']} {v['threshold_unit']}" if v["threshold_value"] else "-",
                    "Status": v["status"],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            st.markdown("#### Verdict detail & citations")
            for v in report["substance_verdicts"]:
                with st.expander(f"{_badge(v['status'])} -- {v['substance_name']} ({v['component_name']})"):
                    st.write(v["explanation"])
                    for c in v["citations"]:
                        st.markdown(f"> **{c['regulation_name']} / {c['clause_id'] or c['source_id']}**\n>\n> {c['text'][:500]}...")
                    if not v["citations"]:
                        st.caption("No regulatory citation -- this substance was not confirmed against the graph.")

            st.info(
                "This is a **screening result for review**, not a legal determination. "
                "Items marked NEEDS_REVIEW require a human decision in the Review Queue tab."
            )

with tab_queue:
    st.subheader("Pending human review items")
    if st.button("Refresh queue"):
        st.rerun()
    try:
        items = requests.get(f"{API_BASE_URL}/review/queue", params={"status": "pending"}, timeout=10).json()
    except requests.RequestException as exc:
        items = []
        st.error(f"Could not reach API: {exc}")

    if not items:
        st.write("No pending review items.")
    for item in items:
        v = item["substance_verdict"]
        with st.container(border=True):
            st.markdown(f"**{v['substance_name']}** in `{v['component_name']}` -- product `{item['product_id']}`")
            st.caption(f"Reason: {item['reason']}")
            st.write(v["explanation"])
            col1, col2, col3 = st.columns([1, 1, 3])
            reviewer = col3.text_input("Reviewer name", key=f"reviewer_{item['id']}", label_visibility="collapsed",
                                        placeholder="Your name")
            if col1.button("Approve", key=f"approve_{item['id']}"):
                requests.post(f"{API_BASE_URL}/review/{item['id']}/decision",
                              json={"decision": "approved", "decided_by": reviewer or "reviewer"}, timeout=10)
                st.rerun()
            if col2.button("Reject", key=f"reject_{item['id']}"):
                requests.post(f"{API_BASE_URL}/review/{item['id']}/decision",
                              json={"decision": "rejected", "decided_by": reviewer or "reviewer"}, timeout=10)
                st.rerun()
