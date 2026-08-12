# app.py
# MDR PepDesign - Main Streamlit Application
# Run with: streamlit run app.py

import streamlit as st
import sys
import os

# ------------------------------------------------------------------
# Always use the project root (D:\mdr-pepdesign) as the working folder
# ------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

os.chdir(PROJECT_ROOT)

# Allow imports from dashboard/
DASHBOARD_DIR = os.path.join(PROJECT_ROOT, "dashboard")

if DASHBOARD_DIR not in sys.path:
    sys.path.insert(0, DASHBOARD_DIR)

# - PAGE CONFIG -
# NOTE: set_page_config() must be the very first Streamlit command that
# runs in the whole script. A leftover debug st.write() used to run
# before this line and made Streamlit raise a StreamlitAPIException,
# which stopped the script right there - that's why most of the app
# (sidebar, CSS, pages) never actually rendered.
st.set_page_config(
    page_title = "MDR PepDesign",
    page_icon  = "🧬",
    layout     = "wide",
    initial_sidebar_state = "expanded"
)

# - IMPORTS -
from utils.styles import inject_css
from utils.ai     import ask_pepdesign
from utils.data   import pipeline_stats
import pages.home     as home
import pages.library  as library
import pages.viewer   as viewer
import pages.results  as results
import pages.new_run  as new_run

# - SIDEBAR (theme picker lives here, BEFORE inject_css runs, so the
#   chosen theme is known before any CSS is written - this was the bug
#   in the previous version: the theme selectbox sat outside the
#   `with st.sidebar:` block due to an indentation slip, so it rendered
#   in the main content area instead of the sidebar, AND inject_css()
#   was called before the theme was even selected so it never received
#   the chosen colors at all) -
with st.sidebar:

    # Brand
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;padding:4px 0;margin-bottom:24px">
      <div style="width:34px;height:34px;border-radius:10px;
      background:linear-gradient(135deg,#7C3AED,#A855F7);
      display:flex;align-items:center;justify-content:center;
      box-shadow:0 4px 16px rgba(124,58,237,0.4);flex-shrink:0">
        <span style="color:#fff;font-size:18px">🧬</span>
      </div>
      <div>
        <div style="font-family:'Syne',sans-serif;font-size:15px;
        font-weight:800;color:#fff;letter-spacing:-.02em">PepDesign</div>
        <div style="font-size:9px;color:#3D4F6B;
        font-family:'JetBrains Mono',monospace;letter-spacing:.05em">
        Design · Predict · Deliver</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Navigation
    st.markdown('<div style="font-size:9px;font-weight:600;color:#3D4F6B;letter-spacing:.1em;text-transform:uppercase;padding:0 4px;margin-bottom:6px">Main</div>', unsafe_allow_html=True)

    page = st.radio(
        "Navigation",
        ["🏠  Dashboard",
         "🔬  3D Viewer",
         "📋  Library",
         "📊  Results",
         "🧪  New Run"],
        label_visibility="collapsed"
    )

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
    st.markdown('<div style="height:0.5px;background:rgba(255,255,255,0.06);margin-bottom:16px"></div>', unsafe_allow_html=True)

    # Target info - reflects the actual receptor used today (AlphaFold
    # model of P23895), not the original 3B5D structure, which turned
    # out to be a CA-only trace and unusable for docking (see
    # PROJECT_SUMMARY.md section 2)
    st.markdown("""
    <div style="background:rgba(124,58,237,0.1);border:0.5px solid rgba(124,58,237,0.25);
    border-radius:10px;padding:10px 12px;margin-bottom:12px">
      <div style="font-family:'JetBrains Mono',monospace;font-size:9px;
      color:#7C3AED;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">
      Active Target</div>
      <div style="font-size:12px;font-weight:600;color:#fff">EmrE · AlphaFold (P23895)</div>
      <div style="font-size:10px;color:#3D4F6B;margin-top:2px">
      MDR efflux pump · rigid peptide docking</div>
    </div>
    """, unsafe_allow_html=True)

    # System status
    st.markdown("""
    <div style="display:flex;align-items:center;gap:6px;padding:6px 4px;margin-bottom:16px">
      <div style="width:6px;height:6px;border-radius:50%;background:#10B981;
      animation:pulse 2s ease-in-out infinite;flex-shrink:0"></div>
      <div style="font-size:10px;color:#3D4F6B">All systems operational</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div style="height:0.5px;background:rgba(255,255,255,0.06);margin-bottom:16px"></div>', unsafe_allow_html=True)

    # Theme picker - now actually inside the sidebar, and selected BEFORE
    # inject_css() runs below
    st.markdown('<div style="font-size:9px;font-weight:600;color:#3D4F6B;letter-spacing:.1em;text-transform:uppercase;padding:0 4px;margin-bottom:6px">Theme</div>', unsafe_allow_html=True)
    theme = st.selectbox(
        "Color scheme",
        ["Deep Navy", "Pure White", "Forest Green", "Midnight Purple"],
        label_visibility="collapsed"
    )

# - INJECT GLOBAL CSS - now theme-aware, runs after theme is selected
inject_css(theme)

# - PROMPT BAR (shown on all pages) -
# Wrapped in the same max-width container styles.py applies to
# .block-container, so it lines up with the page content below instead
# of using its own separate margin values
st.markdown("""
<div style="background:var(--card);border:0.5px solid rgba(124,58,237,0.3);
border-radius:12px;padding:4px 16px;margin-bottom:8px;
box-shadow:0 0 40px rgba(124,58,237,0.08)">
""", unsafe_allow_html=True)

col_icon, col_input, col_btn = st.columns([0.04, 0.88, 0.08])
with col_icon:
    st.markdown('<div style="padding-top:10px;color:#7C3AED;font-size:16px">⬡</div>',
        unsafe_allow_html=True)
with col_input:
    prompt = st.text_input(
        "prompt",
        placeholder="Ask PepDesign anything - 'Best inhibitor for EmrE' or 'Design for PDB 1HVR'",
        label_visibility="collapsed",
        key="main_prompt"
    )
with col_btn:
    run_prompt = st.button("Run →", key="run_prompt")

st.markdown("</div>", unsafe_allow_html=True)

# Quick prompt chips - generated from real pipeline numbers where possible
_stats = pipeline_stats()
_best_dg_chip = f"Show top 10 inhibitors with ΔG below {_stats['best_dG'] + 2:.1f}" \
    if _stats.get("best_dG") is not None else "Show top 10 inhibitors with ΔG below -8.5"

chip_cols = st.columns(5)
chips = [
    "Top inhibitors",
    "Best candidate",
    "Filter safe only",
    "New protein",
    "Compare top 5"
]
chip_prompts = [
    _best_dg_chip,
    "What is the best EmrE inhibitor and why?",
    "Filter by non-hemolytic, charge between 2 and 4",
    "Design inhibitors for a new protein",
    "Compare top 5 candidates by binding affinity"
]

for i, col in enumerate(chip_cols):
    with col:
        if st.button(chips[i], key=f"chip_{i}"):
            prompt = chip_prompts[i]
            run_prompt = True

# - HANDLE PROMPT -
if run_prompt and prompt:
    with st.expander("⬡ PepDesign AI", expanded=True):
        with st.spinner("Thinking..."):
            resp = ask_pepdesign(prompt)
        st.markdown(f"""
        <div style="font-size:13px;color:var(--text);line-height:1.7;
        padding:4px 0">{resp.get("answer","")}</div>
        """, unsafe_allow_html=True)
        steps = resp.get("steps", [])
        if steps:
            st.markdown("---")
            for step in steps:
                st.markdown(f"""
                <div style="font-size:12px;color:#10B981;
                font-family:'JetBrains Mono',monospace;margin-bottom:4px">
                ✓ {step}</div>
                """, unsafe_allow_html=True)

# - RENDER PAGE -
# No extra manual padding wrapper here anymore - .block-container in
# styles.py already provides consistent, proportional page margins,
# so every page (and this prompt bar above) lines up on the same grid
if   "Dashboard" in page: home.render()
elif "3D Viewer" in page: viewer.render()
elif "Library"   in page: library.render()
elif "Results"   in page: results.render()
elif "New Run"   in page: new_run.render()