# pages/peptide_detail.py
# Peptide detail & comparison — a full physicochemical profile plus a
# rotating 3D structure for every peptide shown. Selecting one peptide
# gives a large hero view; selecting 2-3 switches into side-by-side
# comparison mode with an overlaid radar chart. Every structure stays
# 3D and auto-rotating (no static screenshots, no pause toggle).
#
# All numbers shown here (radar chart, stat cards) are computed live
# from the real peptide sequence via utils/peptide_props.py.
#
# Round 1 (DRAMP baseline) vs Round 2 (RFdiffusion novel) badges use
# utils/round_classify.py's length heuristic.
#
# Complex files are read from the CURRENT logged-in user's workspace
# (utils.paths.get_complex_dir()), not a fixed constant.

import os
import streamlit as st
import streamlit.components.v1 as comp
import plotly.graph_objects as go
import pandas as pd

try:
    import py3Dmol
    PY3DMOL_AVAILABLE = True
except ImportError:
    PY3DMOL_AVAILABLE = False

from utils.data import (
    load_top_candidates, RECEPTOR_CHAIN, PEPTIDE_CHAIN,
    BINDING_RESIDUE, PROTEIN_NAME,
)
from utils.paths import get_complex_dir
from utils.peptide_props import compute_properties, RADAR_AXES
from utils.round_classify import round_badge_html

COMPARE_COLORS = ["#E85D24", "#06B6D4", "#A78BFA"]


def _fmt(val, spec="{:.2f}"):
    try:
        if pd.isna(val):
            return "—"
        return spec.format(float(val))
    except (TypeError, ValueError):
        return "—"


def _amino_acid_strip(sequence: str):
    positive = set("KRH")
    negative = set("DE")
    hydrophobic = set("AILMFWYV")
    color_map = {
        **{a: "#3B82F6" for a in positive},
        **{a: "#EF4444" for a in negative},
        **{a: "#F59E0B" for a in hydrophobic},
    }
    chips = "".join(
        f'<span style="display:inline-block;padding:3px 7px;margin:2px;'
        f'border-radius:6px;font-family:\'JetBrains Mono\',monospace;'
        f'font-size:13px;font-weight:600;color:#fff;'
        f'background:{color_map.get(c, "#475569")}">{c}</span>'
        for c in sequence.strip().upper()
    )
    st.markdown(f'<div style="line-height:2.4">{chips}</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="display:flex;gap:14px;margin-top:6px;font-size:10px;color:var(--text3)">
      <span>🔵 positive (K/R/H)</span>
      <span>🔴 negative (D/E)</span>
      <span>🟠 hydrophobic</span>
      <span>⬜ polar / other</span>
    </div>
    """, unsafe_allow_html=True)


def _build_viewer_html(pep_id, complex_dir, height, spin_speed=0.6, surface=True):
    complex_path = os.path.join(complex_dir, f"{pep_id}.pdb")
    if not (PY3DMOL_AVAILABLE and os.path.exists(complex_path)):
        return None

    pdb_str = open(complex_path).read()
    view = py3Dmol.view(width=760, height=height)
    view.addModel(pdb_str, "pdb")

    view.setStyle({"chain": RECEPTOR_CHAIN},
        {"cartoon": {"color": "#7B9BBF", "opacity": 0.82, "thickness": 0.5}})
    view.setStyle({"chain": PEPTIDE_CHAIN},
        {"cartoon": {"color": "#E85D24", "opacity": 1.0}})
    view.addStyle({"chain": PEPTIDE_CHAIN},
        {"stick": {"colorscheme": "orangeCarbon", "radius": 0.28}})
    view.addStyle({"chain": RECEPTOR_CHAIN, "resi": str(BINDING_RESIDUE)},
        {"stick": {"colorscheme": "redCarbon", "radius": 0.4}})

    if surface:
        view.addSurface(py3Dmol.VDW,
            {"opacity": 0.14, "color": "#7B6FFF"},
            {"chain": RECEPTOR_CHAIN})

    view.zoomTo({"chain": PEPTIDE_CHAIN})
    view.zoom(0.7)
    view.setBackgroundColor("#000000", 0)
    view.spin("y", spin_speed)
    return view._make_html()


def _radar_figure(entries):
    fig = go.Figure()
    for label, radar, color in entries:
        values = [radar[a] for a in RADAR_AXES] + [radar[RADAR_AXES[0]]]
        fig.add_trace(go.Scatterpolar(
            r=values, theta=RADAR_AXES + [RADAR_AXES[0]],
            fill="toself", name=label,
            line=dict(color=color, width=2),
            fillcolor=color, opacity=0.35,
        ))
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, range=[0, 1], showticklabels=False,
                             gridcolor="rgba(255,255,255,0.08)"),
            angularaxis=dict(gridcolor="rgba(255,255,255,0.08)", color="#8896B3"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=len(entries) > 1,
        legend=dict(font=dict(color="#8896B3")),
        margin=dict(t=30, b=20, l=40, r=40),
        height=380,
    )
    return fig


def render():
    st.markdown('<div class="section-head">Peptide Detail & Comparison</div>',
        unsafe_allow_html=True)

    complex_dir = get_complex_dir()

    df = load_top_candidates()
    if len(df) == 0:
        st.warning("No candidates found - run docking first.")
        return

    ids = df["id"].tolist()
    picked = st.multiselect(
        "Select 1–3 peptides to inspect",
        ids, default=[ids[0]], max_selections=3,
        help="Pick a second or third peptide to switch into side-by-side comparison mode."
    )

    if not picked:
        st.info("Select at least one peptide above.")
        return

    rows = {pid: df[df["id"] == pid].iloc[0] for pid in picked}
    props = {pid: compute_properties(rows[pid]["sequence"]) for pid in picked}

    if len(picked) == 1:
        _render_single(picked[0], rows[picked[0]], props[picked[0]], complex_dir)
    else:
        _render_compare(picked, rows, props, complex_dir)


def _render_single(pid, row, prop, complex_dir):
    col_view, col_stats = st.columns([1.7, 1])

    with col_view:
        html = _build_viewer_html(pid, complex_dir, height=480)
        if html:
            comp.html(html, height=490)
        else:
            st.markdown(f"""
            <div style="width:100%;height:480px;background:var(--card2);
            border-radius:16px;display:flex;align-items:center;justify-content:center;
            border:0.5px solid var(--border2);text-align:center;color:var(--text3);
            font-family:monospace;font-size:12px;line-height:1.8">
            No 3D complex found for {pid} yet.<br>
            Run <code style="color:#7C3AED">python scripts/build_complexes.py</code>
            </div>""", unsafe_allow_html=True)
        st.caption(f"🔄 Auto-rotating · {PROTEIN_NAME} (chain {RECEPTOR_CHAIN}) "
                   f"+ {pid} (chain {PEPTIDE_CHAIN}) · binding site residue "
                   f"{BINDING_RESIDUE} highlighted in red")

    with col_stats:
        st.markdown(f"""
        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;
        color:#1DC9A8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">
        ◈ {pid}</div>
        """, unsafe_allow_html=True)
        st.markdown(round_badge_html(prop["raw"]["length"]) +
            '<div style="height:10px"></div>', unsafe_allow_html=True)
        _amino_acid_strip(row["sequence"])

        c1, c2 = st.columns(2)
        c1.metric("ΔG (kcal/mol)", _fmt(row.get("dG")))
        c2.metric("ML score", _fmt(row.get("ml_score"), "{:.3f}"))
        c1.metric("Length", f'{prop["raw"]["length"]} aa')
        c2.metric("MW", f'{prop["raw"]["molecular_weight"]:.0f} Da')

    st.markdown("---")
    st.markdown('<div class="section-head" style="font-size:14px">Physicochemical Profile</div>',
        unsafe_allow_html=True)
    st.plotly_chart(_radar_figure([(pid, prop["radar"], "#E85D24")]),
        use_container_width=True)

    with st.expander("Full computed values"):
        st.json(prop["raw"])


def _render_compare(picked, rows, props, complex_dir):
    st.markdown('<div class="section-head" style="font-size:14px">Overlaid Profile</div>',
        unsafe_allow_html=True)
    entries = [(pid, props[pid]["radar"], COMPARE_COLORS[i])
               for i, pid in enumerate(picked)]
    st.plotly_chart(_radar_figure(entries), use_container_width=True)

    st.markdown('<div class="section-head" style="font-size:14px">Structures Side by Side</div>',
        unsafe_allow_html=True)
    cols = st.columns(len(picked))
    for i, pid in enumerate(picked):
        color = COMPARE_COLORS[i]
        with cols[i]:
            st.markdown(f"""
            <div style="border:1.5px solid {color};border-radius:12px;padding:8px">
            <div style="font-family:'JetBrains Mono',monospace;font-size:10px;
            color:{color};font-weight:700;margin-bottom:4px">◈ {pid}</div>
            <div style="margin-bottom:6px">{round_badge_html(props[pid]["raw"]["length"])}</div>
            """, unsafe_allow_html=True)

            html = _build_viewer_html(pid, complex_dir, height=280, spin_speed=0.8, surface=False)
            if html:
                comp.html(html, height=290)
            else:
                st.markdown(f"""
                <div style="width:100%;height:280px;background:var(--card2);
                border-radius:10px;display:flex;align-items:center;justify-content:center;
                color:var(--text3);font-size:11px;text-align:center;padding:10px">
                No complex file for {pid} yet
                </div>""", unsafe_allow_html=True)

            row = rows[pid]
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;margin-top:8px;
            font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text2)">
              <span>ΔG <b style="color:{color}">{_fmt(row.get("dG"))}</b></span>
              <span>ML <b style="color:{color}">{_fmt(row.get("ml_score"), "{:.3f}")}</b></span>
              <span>len <b style="color:{color}">{props[pid]["raw"]["length"]}</b></span>
            </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    numeric_dg = {}
    for pid in picked:
        val = rows[pid].get("dG")
        if pd.notna(val):
            try:
                numeric_dg[pid] = float(val)
            except (TypeError, ValueError):
                pass
    if numeric_dg:
        best_id = min(numeric_dg, key=numeric_dg.get)
        st.markdown(f"""
        <div style="background:rgba(16,185,129,0.08);border:0.5px solid rgba(16,185,129,0.25);
        border-radius:10px;padding:10px 16px;font-size:12px;color:#10B981">
        🏆 <b>{best_id}</b> has the strongest binding affinity in this comparison
        (ΔG = {numeric_dg[best_id]:.2f} kcal/mol).
        </div>
        """, unsafe_allow_html=True)
