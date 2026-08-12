# pages/new_run.py
# Generic protein input — design inhibitors for any protein

import streamlit as st
import json, os, sys, time
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from input_layer import resolve_structure, detect_pocket
from pipeline_runner import start_pipeline_job, get_job_status, list_jobs

def render():
    st.markdown('<div class="section-head">Design for a New Protein</div>',
        unsafe_allow_html=True)

    st.markdown("""
    <div style="font-size:13px;color:#8896B3;margin-bottom:24px;line-height:1.7">
    Submit any target protein — PDB ID or FASTA sequence. The pipeline will
    automatically fetch the structure, detect the binding pocket, and prepare
    everything for peptide inhibitor design.
    </div>
    """, unsafe_allow_html=True)

    # ── INPUT MODE ────────────────────────────────────────────
    mode = st.radio(
        "Input type",
        ["PDB ID (known structure)", "FASTA sequence (novel protein)"],
        horizontal=True
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        if "PDB ID" in mode:
            user_input = st.text_input(
                "PDB ID",
                placeholder="e.g. 3B5D, 1HVR, 4HHB",
                help="4-character PDB identifier from rcsb.org"
            )
        else:
            user_input = st.text_area(
                "FASTA sequence",
                placeholder=">my_protein\nMNPYIYLGGAIL...",
                height=120,
                help="Paste raw FASTA sequence — structure predicted via ESMFold API"
            )
            st.info("Structure will be predicted via ESMFold API — no GPU needed")

    with col2:
        st.markdown("**Binding site (optional)**")
        known_res = st.number_input(
            "Known binding residue",
            value=0,
            min_value=0,
            help="Leave 0 if unknown — P2Rank will detect automatically"
        )
        known_chains = st.text_input(
            "Chains (e.g. A,B)",
            value="",
            help="Leave blank if unknown"
        )
        dg_thresh = st.slider("ΔG threshold", -12.0, -5.0, -8.0)

    # ── RUN BUTTON ────────────────────────────────────────────
    # IMPORTANT: this block only ever executes on the exact script run
    # triggered by clicking the button - st.button() returns True for
    # that one rerun only, then False on every subsequent rerun. Touching
    # ANY other widget afterward (the manual coordinate boxes, the chain
    # field, even the theme picker) triggers a fresh rerun where this
    # entire block is skipped. That used to mean every status message and
    # the manual pocket entry form itself would simply vanish the moment
    # the user tried to interact with them.
    #
    # Fix: this block ONLY does the actual work (resolve structure, detect
    # pocket) and stores results in st.session_state. All of the DISPLAY
    # logic below is intentionally outside this block, so it re-renders
    # from session_state on every rerun regardless of what triggered it.
    if st.button("Run pipeline →") and user_input:
        chains = [c.strip() for c in known_chains.split(",")] \
                  if known_chains else None
        res    = int(known_res) if known_res > 0 else None

        with st.spinner("Fetching and cleaning protein structure..."):
            try:
                pdb_str = resolve_structure(user_input)
                os.makedirs("data", exist_ok=True)
                with open("data/clean_protein.pdb", "w") as f:
                    f.write(pdb_str)
                st.session_state["new_run_protein_pdb"] = "data/clean_protein.pdb"
                st.session_state["new_run_structure_error"] = None
                # Starting a fresh run invalidates any pocket found for a
                # previous protein/input.
                st.session_state["new_run_pocket"] = None
                st.session_state["new_run_pocket_error"] = None
            except Exception as e:
                st.session_state["new_run_structure_error"] = str(e)
                st.session_state["new_run_protein_pdb"] = None

        if st.session_state.get("new_run_protein_pdb"):
            with st.spinner("Detecting binding pocket..."):
                try:
                    coords = detect_pocket(
                        "data/clean_protein.pdb",
                        known_residue=res,
                        known_chains=chains
                    )
                    if coords:
                        with open("data/pocket_coords.txt", "w") as f:
                            json.dump(coords, f, indent=2)
                        st.session_state["new_run_pocket"] = coords
                    st.session_state["new_run_pocket_error"] = None
                except Exception as e:
                    st.session_state["new_run_pocket_error"] = str(e)

    # ── DISPLAY RESULTS ──────────────────────────────────────────
    # Runs on every rerun, sourced entirely from session_state - this is
    # what keeps status messages and the manual-entry form visible while
    # the user is actually typing coordinates into it.
    if st.session_state.get("new_run_structure_error"):
        st.error(f"❌ Failed to resolve structure: {st.session_state['new_run_structure_error']}")

    if st.session_state.get("new_run_protein_pdb"):
        st.success("✅ Structure resolved and cleaned")

        if st.session_state.get("new_run_pocket_error"):
            st.error(f"❌ Pocket detection failed: {st.session_state['new_run_pocket_error']}")
        elif st.session_state.get("new_run_pocket"):
            coords = st.session_state["new_run_pocket"]
            st.success(
                f"✅ Pocket detected via {coords['method']} — "
                f"centre: {coords['cx']:.1f}, "
                f"{coords['cy']:.1f}, {coords['cz']:.1f}"
            )
        else:
            st.warning("⚠️ Could not auto-detect pocket — enter coordinates manually below")

            st.markdown("**Manual binding pocket coordinates**")
            mcol1, mcol2, mcol3 = st.columns(3)
            with mcol1:
                man_cx = st.number_input("Center X", value=0.0, format="%.1f", key="man_cx")
            with mcol2:
                man_cy = st.number_input("Center Y", value=0.0, format="%.1f", key="man_cy")
            with mcol3:
                man_cz = st.number_input("Center Z", value=0.0, format="%.1f", key="man_cz")

            if st.button("Use these coordinates"):
                manual_coords = {
                    "cx": man_cx, "cy": man_cy, "cz": man_cz,
                    "method": "manual"
                }
                with open("data/pocket_coords.txt", "w") as f:
                    json.dump(manual_coords, f, indent=2)
                st.session_state["new_run_pocket"] = manual_coords
                # Immediately re-render with the saved pocket reflected,
                # instead of waiting for an unrelated future interaction.
                st.rerun()

        # Ready message - only shown once a pocket genuinely exists
        # (auto-detected or manually entered above).
        if st.session_state.get("new_run_pocket"):
            st.markdown("""
            <div style="background:rgba(16,185,129,0.08);border:0.5px solid rgba(16,185,129,0.25);
            border-radius:12px;padding:16px 20px;margin-top:16px">
            <div style="font-size:13px;font-weight:600;color:#10B981;margin-bottom:8px">
            ✅ Preparation complete — ready for Person A
            </div>
            <div style="font-size:12px;color:#8896B3;line-height:1.8">
            Hand these two files to Person A:<br>
            <code style="color:#06B6D4">data/clean_protein.pdb</code> — cleaned structure<br>
            <code style="color:#06B6D4">data/pocket_coords.txt</code> — binding pocket coordinates<br><br>
            Person A will run RFdiffusion → ProteinMPNN → ESMFold on Colab GPU.
            Results come back as <code>filtered_peptides.csv</code> + <code>folded/*.pdb</code>.
            </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Enter pocket coordinates above to finish preparing this run.")

    # ── AUTOMATED PIPELINE (new) ───────────────────────────────
    # Only shown once a structure + pocket exist for this session (either
    # just resolved above, or from a previous run) AND a folded peptide
    # set already exists - this runs the SAME validated steps from
    # today's EmrE work (receptor prep, RDKit+meeko rigid ligand prep,
    # auto-sized box, Vina docking), generalized to any protein.
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-head" style="font-size:16px">Automated Docking Run</div>',
        unsafe_allow_html=True)

    protein_pdb = st.session_state.get("new_run_protein_pdb")
    pocket = st.session_state.get("new_run_pocket")
    has_structure = protein_pdb and os.path.exists(protein_pdb)
    has_pocket = pocket is not None

    if not (has_structure and has_pocket):
        st.markdown("""
        <div style="font-size:12px;color:#8896B3;padding:8px 0">
        Run the structure resolution step above first - the automated pipeline
        needs a resolved structure and detected pocket before it can start.
        </div>
        """, unsafe_allow_html=True)
    else:
        folded_dir = st.text_input(
            "Folded peptide directory",
            value="data/folded",
            help="Folder containing *.pdb files (e.g. from Person A's ESMFold step). "
                 "The automated run docks every peptide found here."
        )
        folded_count = len([f for f in os.listdir(folded_dir) if f.endswith(".pdb")]) \
            if os.path.exists(folded_dir) else 0

        if folded_count == 0:
            st.markdown(f"""
            <div style="font-size:12px;color:#8896B3;padding:8px 0">
            No <code>.pdb</code> files found in <code>{folded_dir}</code> yet.
            Once peptides are folded for this protein, point this field at that
            folder and the automated run becomes available.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="font-size:12px;color:#8896B3;padding:8px 0 16px">
            Found <b style="color:#10B981">{folded_count}</b> folded peptides ready to dock.
            This will run receptor prep, ligand prep, and docking automatically -
            the same validated steps used for EmrE, generalized to this protein.
            Expect this to take a while for large peptide sets (hours, not minutes) -
            it's safe to navigate away and come back, progress is saved.
            </div>
            """, unsafe_allow_html=True)

            project_root = st.text_input("Project root folder", value=os.getcwd())

            if st.button("🚀 Start automated docking run"):
                job_id = start_pipeline_job(
                    protein_pdb_path=protein_pdb,
                    pocket_coords=pocket,
                    peptide_folded_dir=folded_dir,
                    project_root=project_root,
                )
                st.session_state["active_job_id"] = job_id
                st.success(f"Job started: {job_id}")
                st.rerun()

    # ── JOB STATUS / PROGRESS ───────────────────────────────────
    active_job = st.session_state.get("active_job_id")
    past_jobs = [j for j in list_jobs() if j != active_job]

    if active_job or past_jobs:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="section-head" style="font-size:16px">Pipeline Jobs</div>',
            unsafe_allow_html=True)

        job_to_show = active_job
        if past_jobs:
            options = ([active_job] if active_job else []) + past_jobs
            job_to_show = st.selectbox("View job", options)

        if job_to_show:
            status = get_job_status(job_to_show)
            stage = status.get("stage", "unknown")
            progress = status.get("progress", 0.0)
            done = status.get("done", False)
            error = status.get("error")

            if error:
                st.error(f"❌ {error}")
            elif done:
                st.success(f"✅ Complete — {status.get('dock_ok', 0)}/{status.get('total_peptides', '?')} docked successfully")
                if status.get("scores_csv"):
                    st.markdown(f"Results: `{status['scores_csv']}`")
            else:
                st.markdown(f"**Stage:** {stage}")
                st.progress(min(max(progress, 0.0), 1.0))
                if "prep_ok" in status:
                    st.markdown(
                        f"<div style='font-size:12px;color:#8896B3'>"
                        f"Prepped: {status.get('prep_ok',0)} · "
                        f"Docked: {status.get('dock_ok',0)} · "
                        f"Failed: {status.get('failed_count',0)} · "
                        f"Total: {status.get('total','?')}"
                        f"</div>", unsafe_allow_html=True
                    )
                # Auto-refresh while a job is actively running, so the user
                # doesn't have to manually reload the page to see progress
                if not done:
                    time.sleep(2)
                    st.rerun()

            log = status.get("log", [])
            if log:
                with st.expander("Job log"):
                    for line in log[-30:]:
                        st.markdown(f"<div style='font-family:monospace;font-size:11px;"
                                     f"color:#8896B3'>{line}</div>", unsafe_allow_html=True)