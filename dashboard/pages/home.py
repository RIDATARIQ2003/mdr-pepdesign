# pages/home.py
# Hero landing page - real EmrE py3Dmol viewer + top candidate stats
# Design: light theme, mockup layout (Space Grotesk, teal/violet accents,
# floating metric cards beside the 3D viewer, pipeline steps strip)

import streamlit as st
import streamlit.components.v1 as comp
import os
from utils.paths import (
    DATA_DIR,
    DOCKING_DIR,
    COMPLEX_DIR,
    FOLDED_DIR,
)

try:
    import py3Dmol
    PY3DMOL_OK = True
except ImportError:
    PY3DMOL_OK = False

from utils.data import (
    load_top_candidates, is_placeholder,
    pipeline_status, pipeline_stats,
    RECEPTOR_CHAIN, PEPTIDE_CHAIN, BINDING_RESIDUE
)


def _pdbqt_to_pdb_string(pdbqt_path, chain_override=None):
    """Convert a PDBQT file to a plain PDB string for py3Dmol.
    PDBQT is PDB + two extra columns (charge, AD atom type) — we just
    truncate those off and optionally relabel the chain."""
    lines = []
    with open(pdbqt_path) as f:
        for line in f:
            if line.startswith("ATOM") or line.startswith("HETATM"):
                pdb_line = "ATOM  " + line[6:66].ljust(60)
                if chain_override:
                    pdb_line = pdb_line[:21] + chain_override + pdb_line[22:]
                lines.append(pdb_line.rstrip() + "\n")
            elif line.startswith("TER") or line.startswith("END"):
                lines.append(line)
    return "".join(lines)


def _residue_centroid(pdb_str, chain, resi):
    """Average x/y/z of all atoms in a given chain+residue, so we can pin
    a floating label directly on the binding site instead of guessing."""
    xs, ys, zs = [], [], []
    for line in pdb_str.splitlines():
        if line.startswith(("ATOM", "HETATM")) and line[21] == chain \
                and line[22:26].strip() == str(resi):
            try:
                xs.append(float(line[30:38]))
                ys.append(float(line[38:46]))
                zs.append(float(line[46:54]))
            except ValueError:
                continue
    if not xs:
        return None
    return {"x": sum(xs) / len(xs), "y": sum(ys) / len(ys), "z": sum(zs) / len(zs)}


def _render_emre_viewer(complex_path, height=520):
    """
    Renders EmrE using py3Dmol.

    Priority:
    1. If docking/receptor_af.pdbqt (or a couple of known alternate names)
       exists — show the protein alone, rotating, with the binding-site
       residue (E14) highlighted and labeled. This is the main view.
    2. If complex_path exists (receptor + docked peptide combined PDB from
       build_complexes.py) — used only as a fallback when the standalone
       receptor file isn't available.
    3. Placeholder if neither file is available.
    """
    if not PY3DMOL_OK:
        comp.html(f"""
        <div style="width:100%;height:{height}px;background:#F4F6FB;
          border-radius:16px;display:flex;align-items:center;justify-content:center;
          border:1px solid #E2E8F4;font-family:monospace;font-size:12px;color:#9AA5BE">
          py3Dmol not installed — run: pip install py3Dmol
        </div>""", height=height + 10)
        return

    # Different naming has floated around this project (receptor_af.pdbqt
    # per data.py's pipeline_status, emre_alphafold per an older note) -
    # check all known candidates instead of hardcoding a single filename.
    RECEPTOR_CANDIDATES = ["receptor_af.pdbqt", "emre_alphafold", "receptor.pdbqt"]
    RECEPTOR_PDBQT = next(
        (DOCKING_DIR / name for name in RECEPTOR_CANDIDATES if os.path.exists(DOCKING_DIR / name)),
        None
    )
    has_complex  = complex_path and os.path.exists(complex_path)
    has_receptor = RECEPTOR_PDBQT is not None

    if not has_complex and not has_receptor:
        # True fallback - neither file exists
        comp.html(f"""
        <div style="width:100%;height:{height}px;
          background:linear-gradient(160deg,#EEF2FB,#F4F6FB);
          border-radius:16px;display:flex;flex-direction:column;
          align-items:center;justify-content:center;
          border:1px solid #E2E8F4">
          <div style="font-size:11px;color:#9AA5BE;text-align:center;line-height:1.8">
            Place <code style="background:#E8EBF4;padding:2px 5px;border-radius:4px">
            receptor_af.pdbqt</code> in the<br>
            <code style="background:#E8EBF4;padding:2px 5px;border-radius:4px">
            docking/</code> folder to see EmrE here.
          </div>
        </div>""", height=height + 10)
        return

    view = py3Dmol.view(width=760, height=height)

    if has_receptor:
        # Protein alone — convert PDBQT inline, spin so you can see EmrE
        # from every angle. The binding-site residue (E14) is highlighted
        # with a thicker stick style plus a floating label pinned right
        # on the pocket, so it reads clearly even while rotating.
        pdb_str = _pdbqt_to_pdb_string(RECEPTOR_PDBQT, chain_override=RECEPTOR_CHAIN)
        view.addModel(pdb_str, "pdb")
        view.setStyle({"chain": RECEPTOR_CHAIN},
                      {"cartoon": {"color": "#7B9BBF", "opacity": 0.95, "thickness": 0.5}})
        view.addStyle({"chain": RECEPTOR_CHAIN, "resi": str(BINDING_RESIDUE)},
                      {"stick": {"colorscheme": "orangeCarbon", "radius": 0.45}})
        view.addSurface(py3Dmol.VDW,
                        {"opacity": 0.16, "color": "#7B6FFF"},
                        {"chain": RECEPTOR_CHAIN})
        # A subtle dark outline reads much better on a light card than a
        # flat cartoon alone - gives the model more visual "weight".
        view.setViewStyle({"style": "outline", "color": "#0D1829", "width": 0.04})

        centroid = _residue_centroid(pdb_str, RECEPTOR_CHAIN, BINDING_RESIDUE)
        if centroid:
            view.addLabel(f"Binding site · E{BINDING_RESIDUE}", {
                "position": centroid,
                "backgroundColor": "#FF7A59",
                "backgroundOpacity": 0.9,
                "fontColor": "white",
                "fontSize": 13,
                "borderRadius": 6,
                "inFront": True,
            })

        view.zoomTo()
        view.zoom(1.1)
        view.spin("y", 0.4)  # slow, cinematic rotation
    elif has_complex:
        # Fallback: full complex (receptor + docked peptide), only used
        # when the standalone receptor file isn't available.
        pdb_str = open(complex_path).read()
        view.addModel(pdb_str, "pdb")
        view.setStyle({"chain": RECEPTOR_CHAIN},
                      {"cartoon": {"color": "#7B9BBF", "opacity": 0.85, "thickness": 0.5}})
        view.setStyle({"chain": PEPTIDE_CHAIN},
                      {"cartoon": {"color": "#FF7A59", "opacity": 1.0}})
        view.addStyle({"chain": PEPTIDE_CHAIN},
                      {"stick": {"colorscheme": "orangeCarbon", "radius": 0.25}})
        view.addSurface(py3Dmol.VDW,
                        {"opacity": 0.12, "color": "#7B6FFF"},
                        {"chain": RECEPTOR_CHAIN})
        view.setViewStyle({"style": "outline", "color": "#0D1829", "width": 0.04})
        view.zoomTo({"chain": PEPTIDE_CHAIN})
        view.zoom(0.55)
        view.spin("y", 0.4)

    # Transparent background so the page's own hero-stage gradient shows
    # through the canvas instead of a flat rectangle.
    view.setBackgroundColor("#000000", 0)
    html = view._make_html()
    comp.html(html, height=height + 10)


def render():
    # Load data first so real numbers flow into every section below
    df  = load_top_candidates()
    top = df.iloc[0] if len(df) > 0 else None
    stats = pipeline_stats()
    status = pipeline_status()

    # Find the best complex file to show — top candidate if available,
    # otherwise fall back to any complex that exists
    complex_path = None
    if top is not None:
        candidate_path = os.path.join(COMPLEX_DIR, f"{top.get('id','')}.pdb")
        if os.path.exists(candidate_path):
            complex_path = candidate_path
    if complex_path is None:
        # fallback: first available complex
        if os.path.exists(COMPLEX_DIR):
            files = [f for f in os.listdir(COMPLEX_DIR) if f.endswith(".pdb")]
            if files:
                complex_path = os.path.join(COMPLEX_DIR, sorted(files)[0])

    # ── FONT + PAGE-LEVEL STYLE ─────────────────────────────────
    # Override the app-wide CSS just for this page's signature elements.
    # Space Grotesk for display headings matches the mockup; everything
    # else inherits from styles.py (Inter body, JetBrains Mono for data).
    #
    # IMPORTANT: the <link> tag and <style> block are sent as TWO separate
    # st.markdown() calls, not one. Markdown's raw-HTML parser treats
    # <style>/<script>/<pre> as "type 1" blocks that stay raw until their
    # matching closing tag, blank lines and all - but <link> is a "type 6"
    # tag that ends at the FIRST blank line. When <link> was the first tag
    # in the same block as <style>, the whole thing got parsed under the
    # type-6 rule, so the first blank line inside the CSS (there are many)
    # closed the block early and everything after it fell back to being
    # rendered as plain text - which is exactly the raw CSS text leaking
    # onto the page. Starting a fresh block with <style> as the very first
    # tag avoids this entirely.
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
    """, unsafe_allow_html=True)

    st.markdown("""
    <style>
    /* ---- PepDesign home page styles ---- */
    .pg-title{
        font-family:'Space Grotesk',sans-serif;
        font-size:22px; font-weight:700;
        color:#0D1829; line-height:1.2; margin-bottom:4px;
    }
    .pg-sub{font-size:13px; color:#6B7A99; margin-bottom:20px;}
    .pg-tag{
        display:inline-flex; align-items:center; gap:5px;
        font-size:11px; font-weight:500; color:#7B6FFF;
        background:rgba(123,111,255,0.1); border-radius:999px;
        padding:3px 10px; margin-left:10px; vertical-align:middle;
    }

    /* Hero stage — light card with a very subtle radial glow,
       matches the mockup's stage element adapted for light theme */
    .hero-stage{
        background: radial-gradient(ellipse at 50% 80%,
            rgba(29,201,168,0.10) 0%, rgba(123,111,255,0.06) 45%, transparent 70%),
            #FFFFFF;
        border: 1px solid #E2E8F4;
        border-radius: 20px;
        padding: 0;
        overflow: hidden;
        position: relative;
    }

    /* Floating metric cards — glassmorphism on light bg */
    .metric-float{
        background: rgba(255,255,255,0.92);
        backdrop-filter: blur(8px);
        border: 1px solid #E2E8F4;
        border-radius: 14px;
        padding: 14px 16px;
    }
    .metric-label{
        font-family:'JetBrains Mono',monospace;
        font-size:9px; color:#9AA5BE;
        text-transform:uppercase; letter-spacing:.08em;
        margin-bottom:4px;
    }
    .metric-val{
        font-family:'Space Grotesk',sans-serif;
        font-size:26px; font-weight:700; line-height:1;
    }
    .metric-unit{font-size:11px; color:#9AA5BE; margin-top:3px;}

    /* Mini bar */
    .mini-bar-track{
        height:3px; background:#EEF0F7;
        border-radius:3px; margin-top:8px; overflow:hidden;
    }
    .mini-bar-fill{height:100%; border-radius:3px;}

    /* Sequence pill */
    .seq-pill{
        font-family:'JetBrains Mono',monospace;
        font-size:13px; font-weight:500;
        color:#1DC9A8;
        background:rgba(29,201,168,0.08);
        border:1px solid rgba(29,201,168,0.2);
        border-radius:8px; padding:8px 14px;
        letter-spacing:.08em; margin-bottom:14px;
    }

    /* Pipeline strip */
    .pipe-strip{
        display:grid;
        grid-template-columns:repeat(5,1fr);
        gap:10px; margin-top:4px;
    }
    .pipe-step{
        background:#FFFFFF; border:1px solid #E8EBF4;
        border-radius:12px; padding:12px 14px;
    }
    .pipe-step.current{
        border-color:#1DC9A8;
        box-shadow:0 0 0 1px rgba(29,201,168,0.3),
                   0 4px 14px rgba(29,201,168,0.12);
    }
    .pipe-n{
        width:22px; height:22px; border-radius:6px;
        background:#F0F2FA; color:#9AA5BE;
        font-family:'Space Grotesk',sans-serif;
        font-size:11px; font-weight:600;
        display:flex; align-items:center; justify-content:center;
        margin-bottom:8px;
    }
    .pipe-step.current .pipe-n{background:#1DC9A8; color:#fff;}
    .pipe-b{font-size:12px; font-weight:600; color:#0D1829; margin-bottom:2px;}
    .pipe-s{font-size:10.5px; color:#9AA5BE; line-height:1.4;}

    /* Stat cards row */
    .stat-strip{display:grid; grid-template-columns:repeat(4,1fr); gap:12px;}
    .stat-box{
        background:#FFFFFF; border:1px solid #E8EBF4;
        border-radius:14px; padding:16px 18px;
    }
    .stat-box .lbl{
        font-family:'JetBrains Mono',monospace;
        font-size:9px; color:#9AA5BE;
        text-transform:uppercase; letter-spacing:.08em; margin-bottom:6px;
    }
    .stat-box .num{
        font-family:'Space Grotesk',sans-serif;
        font-size:28px; font-weight:700; color:#0D1829; line-height:1;
    }
    .stat-box .sub{font-size:11px; color:#9AA5BE; margin-top:4px;}
    
    /* Pipeline status pills */
    .status-pill{
        display:inline-flex; align-items:center; gap:5px;
        font-size:10px; padding:3px 9px; border-radius:99px;
        margin:3px;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── TOPBAR ────────────────────────────────────────────────
    if is_placeholder():
        st.markdown("""
        <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;
        padding:10px 16px;margin-bottom:14px;font-size:12px;color:#92400E;">
        ⏳ <b>Placeholder data</b> — docking_scores.csv not found.
        Real results load automatically once docking completes.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="pg-title">
        AI-driven MDR PepDesign
        <span class="pg-tag">✦ AI-powered</span>
    </div>
    <div class="pg-sub">
        Generative peptide inhibitors for bacterial efflux pumps —
        designed by AI, validated by science.
    </div>
    """, unsafe_allow_html=True)

    # ── HERO (viewer + metric cards side by side) ─────────────
    # Two columns: wider left for the actual 3D viewer, narrower right
    # for the metric cards (same proportion as your mockup's stage vs
    # the right-panel design goals card). Can't float cards ON TOP of
    # an iframe, so we put them beside it instead — cleaner on light bg.
    col_viewer, col_metrics = st.columns([1.8, 1])

    with col_viewer:
        st.markdown('<div class="hero-stage">', unsafe_allow_html=True)

        # Label pinned to top-left corner of the stage
        st.markdown("""
        <div style="position:absolute;top:14px;left:14px;z-index:10;
          background:rgba(255,255,255,0.92);backdrop-filter:blur(6px);
          border:1px solid #E2E8F4;border-radius:8px;
          padding:5px 10px;font-family:monospace;font-size:10px;color:#7B6FFF">
          AlphaFold · EmrE (P23895)
        </div>
        """, unsafe_allow_html=True)

        _render_emre_viewer(complex_path or "", height=520)

        st.markdown("""
        <div style="position:absolute;bottom:14px;right:14px;
          background:rgba(255,255,255,0.92);backdrop-filter:blur(6px);
          border:1px solid rgba(255,122,89,0.3);border-radius:999px;
          padding:5px 12px;font-size:10px;color:#FF7A59;font-family:monospace;
          display:flex;align-items:center;gap:6px">
          <span style="width:6px;height:6px;border-radius:50%;
          background:#FF7A59;display:inline-block"></span>
          Rigid peptide docking
        </div>
        """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    with col_metrics:
        if top is not None:
            dg  = top.get("dG", "—")
            ml  = top.get("ml_score", "—")
            seq = top.get("sequence", "—")
            rank_id = top.get("id", "—")

            # Rank label
            st.markdown(f"""
            <div style="font-family:'JetBrains Mono',monospace;font-size:9px;
              color:#1DC9A8;text-transform:uppercase;letter-spacing:.1em;
              margin-bottom:10px">◈ Novel inhibitor · Rank #1</div>
            <div style="font-family:'Space Grotesk',sans-serif;font-size:22px;
              font-weight:700;color:#0D1829;line-height:1.2;margin-bottom:6px">
              Your best<br>
              <span style="background:linear-gradient(135deg,#1DC9A8,#7B6FFF);
              -webkit-background-clip:text;-webkit-text-fill-color:transparent">
              peptide inhibitor</span>
            </div>
            <div style="font-size:12px;color:#6B7A99;margin-bottom:14px;line-height:1.7">
              AI-designed and computationally validated.<br>
              Binds EmrE — blocks MDR drug efflux.
            </div>
            <div class="seq-pill">{seq}</div>
            """, unsafe_allow_html=True)

            # Binding ΔG card
            dg_pct = min(abs(float(dg)) / 12.0 * 100, 100) if dg != "—" else 0
            st.markdown(f"""
            <div class="metric-float" style="margin-bottom:10px">
              <div class="metric-label">Binding ΔG</div>
              <div class="metric-val" style="color:#7B6FFF">{dg}</div>
              <div class="metric-unit">kcal/mol</div>
              <div class="mini-bar-track">
                <div class="mini-bar-fill"
                  style="width:{dg_pct:.0f}%;background:#7B6FFF"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ML score card
            ml_pct = float(ml) * 100 if ml != "—" else 0
            st.markdown(f"""
            <div class="metric-float">
              <div class="metric-label">ML activity score</div>
              <div class="metric-val" style="color:#1DC9A8">{ml}</div>
              <div class="metric-unit">activity probability</div>
              <div class="mini-bar-track">
                <div class="mini-bar-fill"
                  style="width:{ml_pct:.0f}%;background:#1DC9A8"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.markdown("""
            <div style="color:#9AA5BE;font-size:13px;padding:40px 0">
            No candidates found yet.<br>
            Run the docking pipeline to populate results.
            </div>
            """, unsafe_allow_html=True)

    # ── PIPELINE STEPS STRIP ─────────────────────────────────
    done_steps = sum(status.values())
    total_steps = len(status)
    st.markdown(f"""
    <div style="margin:20px 0 10px;display:flex;align-items:center;
      justify-content:space-between">
      <div style="font-family:'Space Grotesk',sans-serif;font-size:14px;
        font-weight:600;color:#0D1829">Pipeline progress</div>
      <div style="font-size:11px;color:#9AA5BE">{done_steps}/{total_steps} steps complete</div>
    </div>
    <div class="pipe-strip">
      <div class="pipe-step {'current' if not status.get('ML model trained') else ''}">
        <div class="pipe-n">1</div>
        <div class="pipe-b">Target input</div>
        <div class="pipe-s">PDB ID or FASTA</div>
      </div>
      <div class="pipe-step {'current' if status.get('Dataset collected') and not status.get('ML model trained') else ''}">
        <div class="pipe-n">2</div>
        <div class="pipe-b">ML screening</div>
        <div class="pipe-s">AMP classifier</div>
      </div>
      <div class="pipe-step {'current' if status.get('ML model trained') and not status.get('Docking complete') else ''}">
        <div class="pipe-n">3</div>
        <div class="pipe-b">Folding</div>
        <div class="pipe-s">ESMFold prediction</div>
      </div>
      <div class="pipe-step {'current' if status.get('Receptor prepared') and not status.get('Docking complete') else ''}">
        <div class="pipe-n">4</div>
        <div class="pipe-b">Docking</div>
        <div class="pipe-s">AutoDock Vina</div>
      </div>
      <div class="pipe-step {'current' if status.get('Docking complete') else ''}">
        <div class="pipe-n">5</div>
        <div class="pipe-b">Final selection</div>
        <div class="pipe-s">Top binders ranked</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── STAT CARDS ROW ────────────────────────────────────────
    st.markdown("""
    <div style="margin:20px 0 10px;font-family:'Space Grotesk',sans-serif;
      font-size:14px;font-weight:600;color:#0D1829">Summary</div>
    """, unsafe_allow_html=True)

    folded   = f'{stats["total_folded"]:,}' if stats.get("total_folded") else "—"
    screened = f'{stats["ml_screened"]:,}'  if stats.get("ml_screened")  else "—"
    top_n    = str(stats["top_candidates"]) if stats.get("top_candidates") is not None else "—"
    best_dg  = f'{stats["best_dG"]:.2f}'   if stats.get("best_dG")       else "—"

    st.markdown(f"""
    <div class="stat-strip">
      <div class="stat-box">
        <div class="lbl">Peptides folded</div>
        <div class="num">{folded}</div>
        <div class="sub">ESMFold via Person A</div>
      </div>
      <div class="stat-box">
        <div class="lbl">ML screened</div>
        <div class="num">{screened}</div>
        <div class="sub">AMP classifier</div>
      </div>
      <div class="stat-box">
        <div class="lbl">Top candidates</div>
        <div class="num">{top_n}</div>
        <div class="sub">ΔG ≤ −8.0 kcal/mol</div>
      </div>
      <div class="stat-box">
        <div class="lbl">Best ΔG</div>
        <div class="num">{best_dg}</div>
        <div class="sub">kcal/mol</div>
      </div>
    </div>
    """, unsafe_allow_html=True)