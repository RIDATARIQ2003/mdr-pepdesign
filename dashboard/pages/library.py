# pages/library.py
# Peptide library — browse, filter, download all candidates
#
# Real columns in master_results.csv: id, dG, sequence, length, ml_score

import streamlit as st
from utils.data import load_master_results
from utils.paths import (
    DATA_DIR,
    DOCKING_DIR,
    COMPLEX_DIR,
    FOLDED_DIR,
)


def render():
    st.markdown('<div class="section-head">Peptide Inhibitor Library</div>',
        unsafe_allow_html=True)

    df = load_master_results()

    if len(df) == 0:
        st.warning("No results found - run docking first.")
        return

    # ── FILTERS ───────────────────────────────────────────────
    has_ml_score = "ml_score" in df.columns and df["ml_score"].notna().any()
    col1, col2 = st.columns(2) if has_ml_score else st.columns(1)

    with col1:
        dg_max = st.slider("Max ΔG (kcal/mol)", -12.0, -5.0, -8.0, 0.1)

    if has_ml_score:
        with col2:
            ml_min = st.slider("Min ML score", 0.0, 1.0, 0.0, 0.05)

    # Apply filters
    filtered = df[df["dG"] <= dg_max] if "dG" in df.columns else df
    if has_ml_score:
        filtered = filtered[filtered["ml_score"] >= ml_min]

    st.markdown(f"""
    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;
    color:#3D4F6B;margin-bottom:12px">
    Showing {len(filtered)} of {len(df)} candidates
    </div>
    """, unsafe_allow_html=True)

    # ── TABLE ─────────────────────────────────────────────────
    display_cols = [c for c in ["id", "sequence", "length", "dG", "ml_score"]
                     if c in filtered.columns]

    st.dataframe(
        filtered[display_cols].sort_values("dG").reset_index(drop=True),
        use_container_width=True,
        height=400
    )

    # ── DOWNLOAD ──────────────────────────────────────────────
    st.download_button(
        "⬇ Download filtered candidates (CSV)",
        filtered.to_csv(index=False),
        "pepdesign_candidates.csv",
        "text/csv"
    )