"""
app.py
---------------------------------
AI Clinical Data QC & Query Assistant — Streamlit front end.

Two tabs:
  1. Ask a Question  — natural-language interface over ADSL/ADAE
  2. Data QC Dashboard — derivation-logic checks beyond Pinnacle 21

Run:
    export ANTHROPIC_API_KEY=sk-...
    streamlit run app.py
"""

import os
import sys
import pandas as pd
import streamlit as st

sys.path.append(os.path.join(os.path.dirname(__file__), "qc"))
sys.path.append(os.path.join(os.path.dirname(__file__), "nl"))

from qc_checks import run_all_checks, summarize_results  # noqa: E402

st.set_page_config(page_title="AI Clinical Data QC & Query Assistant", layout="wide")


@st.cache_data
def load_data():
    base = os.path.join(os.path.dirname(__file__), "data")
    adsl = pd.read_csv(os.path.join(base, "adsl.csv"), dtype=str)
    adae = pd.read_csv(os.path.join(base, "adae.csv"), dtype=str)
    adae["ASEQ"] = pd.to_numeric(adae["ASEQ"], errors="coerce")
    adae["AVISITN"] = pd.to_numeric(adae["AVISITN"], errors="coerce")
    adae["AETOXGR"] = pd.to_numeric(adae["AETOXGR"], errors="coerce")
    return adsl, adae


adsl, adae = load_data()

st.title("🧪 AI Clinical Data QC & Query Assistant")
st.caption(
    "Synthetic ADaM data (ADSL/ADAE) — natural-language querying + "
    "derivation-logic QC checks beyond standard Pinnacle 21 compliance rules."
)

tab1, tab2 = st.tabs(["💬 Ask a Question", "✅ Data QC Dashboard"])

# ---------------------------------------------------------------- TAB 1
with tab1:
    st.subheader("Ask a question about the study data")
    st.write(
        "Examples: *\"Which subjects discontinued due to an adverse event, "
        "and what was their treatment arm?\"* or *\"How many subjects in the "
        "safety population had a Grade 3 or higher AE after Visit 4?\"*"
    )

    api_key_present = bool(os.environ.get("GEMINI_API_KEY"))
    if not api_key_present:
        st.warning(
            "GEMINI_API_KEY is not set in this environment. Get a free key "
            "(no credit card) at https://aistudio.google.com/apikey and set "
            "it before running to enable natural-language querying."
        )

    question = st.text_input("Your question", "")
    if st.button("Ask", disabled=not api_key_present) and question:
        from query_engine import ask  # imported lazily so the app loads without the key

        with st.spinner("Generating query and analyzing..."):
            try:
                out = ask(question, adsl, adae)
                st.markdown("**Answer:**")
                st.write(out["summary"])

                with st.expander("Show generated query and raw result"):
                    st.code(out["expression"], language="python")
                    result = out["result"]
                    if isinstance(result, (pd.DataFrame, pd.Series)):
                        st.dataframe(result)
                    else:
                        st.write(result)
            except Exception as e:
                st.error(f"Something went wrong: {e}")

# ---------------------------------------------------------------- TAB 2
with tab2:
    st.subheader("Derivation-logic QC checks")
    st.write(
        "These checks catch internal-consistency issues in the derivation "
        "logic — things a compliance tool like Pinnacle 21 typically won't "
        "flag because they're not CDISC controlled-terminology or "
        "structure violations."
    )

    results = run_all_checks(adsl, adae)
    summary_df = summarize_results(results)

    def highlight_severity(row):
        color = {"HIGH": "#ffe0e0", "MEDIUM": "#fff6d5", "LOW": "#e6f4ea"}.get(row["Severity"], "")
        return [f"background-color: {color}"] * len(row)

    st.dataframe(summary_df.style.apply(highlight_severity, axis=1), use_container_width=True)

    total_flagged = summary_df["Records Flagged"].sum()
    high_severity_checks = (summary_df["Severity"] == "HIGH").sum()
    col1, col2, col3 = st.columns(3)
    col1.metric("Total records flagged", int(total_flagged))
    col2.metric("High-severity checks with issues", int(((summary_df["Severity"] == "HIGH") & (summary_df["Records Flagged"] > 0)).sum()))
    col3.metric("Checks run", len(results))

    st.divider()
    st.markdown("### Flagged records by check")
    for r in results:
        if r.n_flagged > 0:
            with st.expander(f"{r.check_id} — {r.description} ({r.n_flagged} flagged)"):
                st.dataframe(r.flagged, use_container_width=True)
