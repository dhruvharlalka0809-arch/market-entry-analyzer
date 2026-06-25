import os

import streamlit as st

from pipeline import run_analysis

st.set_page_config(page_title="Market Entry Analyzer", layout="wide")

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error("Please set ANTHROPIC_API_KEY in your environment before running this app.")
    st.stop()

st.title("Market Entry Strategic Analysis")
st.markdown(
    "Enter a market entry question with a **specific company** and a "
    "**specific market/segment**. The tool will produce a sourced, "
    "verified analysis with decision thresholds."
)

question = st.text_area(
    "Business question",
    placeholder="e.g. Should Spotify enter the podcast advertising market in Southeast Asia?",
    height=100,
)

competitors = st.text_input(
    "Known competitors (optional)",
    placeholder="e.g. iHeartMedia, Acast, SXM Media",
)

if st.button("Analyze", type="primary", disabled=not question.strip()):
    status_container = st.status("Starting analysis...", expanded=True)

    def update_status(msg: str):
        status_container.update(label=msg)
        status_container.write(msg)

    result = run_analysis(
        question=question.strip(),
        competitors=competitors.strip(),
        on_status=update_status,
    )

    if result.error:
        is_clarification = result.error.startswith("clarification_needed:")

        if is_clarification:
            status_container.update(label="More detail needed", state="complete")
            clarifying_q = result.error.replace("clarification_needed:", "", 1)
            st.warning(f"Please provide more detail: {clarifying_q}")
        else:
            status_container.update(label="Error", state="error")
            st.error(result.error)
    else:
        status_container.update(label="Analysis complete", state="complete")
        st.markdown(result.report)
