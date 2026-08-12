# pages/results.py
# Full results — charts, scatter plot, results table
#
# Real columns in master_results.csv: id, dG, sequence, length, ml_score
# (confirmed against the actual file - no charge/safe/ipTM/pTM data exists,
# those were placeholder-only fields from before real docking results existed)

import streamlit as st
import plotly.express as px
from utils.data import load_master_results, load_docking_scores
from utils.paths import (
    DATA_DIR,
    DOCKING_DIR,
    COMPLEX_DIR,
    FOLDED_DIR,
)

PLOTLY_THEME = {
    "paper_bgcolor": "#0A1628",
    "plot_bgcolor": "#0A1628",
    "font": {"color": "#8896B3", "family": "JetBrains Mono"},
    "xaxis": {"gridcolor": "rgba(255,255,255,0.05)", "color": "#3D4F6B"},
    "yaxis": {"gridcolor": "rgba(255,255,255,0.05)", "color": "#3D4F6B"},
}


def render():
    st.markdown('<div class="section-head">Results & Analysis</div>',
        unsafe_allow_html=True)

    df = load_master_results()
    docking = load_docking_scores()

    if len(docking) == 0:
        st.warning("No docking results found - run the docking pipeline first.")
        return

    # ── ROW 1 — TWO CHARTS ───────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        fig = px.histogram(
            docking, x="dG", nbins=30,
            title="Docking Score Distribution",
            color_discrete_sequence=["#7C3AED"]
        )
        fig.add_vline(x=-8.0, line_dash="dash", line_color="#E85D24",
            annotation_text="Threshold −8.0", annotation_font_color="#E85D24")
        fig.update_layout(**PLOTLY_THEME,
            title_font={"color": "#fff", "size": 13},
            margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        top20 = docking.nsmallest(20, "dG")
        fig2 = px.bar(
            top20, x="dG", y="id", orientation="h",
            title="Top 20 Inhibitors by Binding Affinity",
            color_discrete_sequence=["#06B6D4"]
        )
        # Build a single combined theme dict instead of passing yaxis twice
        # (PLOTLY_THEME already has a "yaxis" key - passing both **PLOTLY_THEME
        # and a separate yaxis= kwarg crashes with a duplicate-keyword
        # TypeError, caught by testing today). Merge the override into the
        # theme's yaxis dict instead.
        theme_with_reversed_yaxis = {
            **PLOTLY_THEME,
            "yaxis": {**PLOTLY_THEME["yaxis"], "autorange": "reversed", "tickfont": {"size": 9}},
        }
        fig2.update_layout(**theme_with_reversed_yaxis,
            title_font={"color": "#fff", "size": 13},
            margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig2, use_container_width=True)

    # ── ROW 2 — ML SCORE VS BINDING AFFINITY ─────────────────
    if "ml_score" in df.columns and df["ml_score"].notna().any():
        fig3 = px.scatter(
            df, x="ml_score", y="dG",
            title="ML Score vs Binding Affinity",
            color_discrete_sequence=["#A78BFA"],
            hover_data=["id", "sequence"] if "sequence" in df.columns else ["id"]
        )
        fig3.add_hline(y=-8.0, line_dash="dash", line_color="#E85D24")
        fig3.update_layout(**PLOTLY_THEME,
            title_font={"color": "#fff", "size": 13},
            margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig3, use_container_width=True)

    # ── FULL RESULTS TABLE ────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-head" style="font-size:14px">Full Results Table</div>',
        unsafe_allow_html=True)

    display_cols = [c for c in ["id", "sequence", "length", "dG", "ml_score"]
                     if c in df.columns]

    st.dataframe(
        df[display_cols].sort_values("dG").reset_index(drop=True),
        use_container_width=True,
        height=350
    )

    st.download_button(
        "⬇ Download master_results.csv",
        df.to_csv(index=False),
        "master_results.csv",
        "text/csv"
    )