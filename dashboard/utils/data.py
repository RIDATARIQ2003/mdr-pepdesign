# utils/data.py
# Data loader - uses real CSV files when available
# Falls back to placeholder data while files are missing

import pandas as pd
import os
from utils.paths import (
    DATA_DIR,
    DOCKING_DIR,
    COMPLEX_DIR,
    FOLDED_DIR,
)

# ============================================================
# SETTINGS - reflects the validated pipeline (see PROJECT_SUMMARY.md)
# ============================================================
PROTEIN_NAME     = "EmrE"
PROTEIN_SOURCE   = "AlphaFold (UniProt P23895)"   # NOT 3B5D - that structure
                                                    # was found to be CA-only
                                                    # and unusable for docking
BINDING_RESIDUE  = 14
RECEPTOR_CHAIN   = "A"   # must match scripts/build_complexes.py RECEPTOR_CHAIN
PEPTIDE_CHAIN    = "C"   # must match scripts/build_complexes.py PEPTIDE_CHAIN
DG_THRESHOLD     = -8.0
# DATA_DIR is imported from utils.paths above - do NOT redefine it here.
# It used to be re-declared as the plain string "data", which silently
# threw away the absolute path from paths.py and only "worked" by luck
# because app.py happens to os.chdir() into the project root. Once
# paths.py's ROOT is correct, using the imported Path object directly
# is more robust (works regardless of the current working directory).
TOTAL_FOLDED     = 341    # peptides Person A successfully folded with ESMFold
# ============================================================

# - PLACEHOLDER DATA -
# Used only if real CSVs are missing - lets the dashboard render something
# sensible before/without real data, same fallback pattern as before

PLACEHOLDER_CANDIDATES = pd.DataFrame([
    {"id":"pep_001","sequence":"KLFLKKLKSIF","length":11,"dG":-9.4,"ml_score":0.92,"ipTM":0.74,"pTM":0.68,"charge":3.2,"hydrophobicity":-0.45,"instability":28.4,"safe":True},
    {"id":"pep_002","sequence":"RWLKFLRKILS","length":11,"dG":-9.1,"ml_score":0.88,"ipTM":0.71,"pTM":0.65,"charge":3.8,"hydrophobicity":-0.38,"instability":31.2,"safe":True},
    {"id":"pep_003","sequence":"KLFWRKLKSAF","length":11,"dG":-8.9,"ml_score":0.85,"ipTM":0.68,"pTM":0.62,"charge":3.1,"hydrophobicity":-0.52,"instability":29.8,"safe":True},
    {"id":"pep_004","sequence":"ILKWRFLKKAL","length":11,"dG":-8.7,"ml_score":0.81,"ipTM":0.65,"pTM":0.59,"charge":2.9,"hydrophobicity":-0.41,"instability":33.1,"safe":False},
    {"id":"pep_005","sequence":"RLWKFLKSIFK","length":11,"dG":-8.6,"ml_score":0.79,"ipTM":0.63,"pTM":0.57,"charge":3.4,"hydrophobicity":-0.48,"instability":27.6,"safe":True},
    {"id":"pep_006","sequence":"KLFRWILKKAF","length":11,"dG":-8.4,"ml_score":0.76,"ipTM":0.61,"pTM":0.55,"charge":3.0,"hydrophobicity":-0.44,"instability":30.5,"safe":True},
    {"id":"pep_007","sequence":"WLKRFLKKSIF","length":11,"dG":-8.3,"ml_score":0.74,"ipTM":0.60,"pTM":0.54,"charge":2.8,"hydrophobicity":-0.50,"instability":32.3,"safe":True},
    {"id":"pep_008","sequence":"KLFRKWILSAF","length":11,"dG":-8.2,"ml_score":0.71,"ipTM":0.58,"pTM":0.52,"charge":3.3,"hydrophobicity":-0.39,"instability":35.7,"safe":False},
])

def load_docking_scores():
    """Load docking scores - real or placeholder."""
    path = os.path.join(DATA_DIR, "docking_scores.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return PLACEHOLDER_CANDIDATES[["id","dG"]].copy()

def load_top_candidates():
    """Load top candidates - real or placeholder."""
    path = os.path.join(DATA_DIR, "top_candidates.csv")
    if os.path.exists(path):
        df = pd.read_csv(path)
        # Merge with master_results for sequence/ml_score if top_candidates
        # itself doesn't already have them (top_candidates.csv from
        # parse_results.py only has id + dG)
        if "sequence" not in df.columns:
            master_path = os.path.join(DATA_DIR, "master_results.csv")
            if os.path.exists(master_path):
                master = pd.read_csv(master_path)
                extra_cols = [c for c in master.columns if c not in df.columns or c == "id"]
                df = df.merge(master[extra_cols], on="id", how="left")
        return df.sort_values("dG").reset_index(drop=True)
    return PLACEHOLDER_CANDIDATES.copy()

def load_master_results():
    """Load full master results (docking + ML scores merged) - real or placeholder."""
    path = os.path.join(DATA_DIR, "master_results.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return PLACEHOLDER_CANDIDATES.copy()

def load_filtered_peptides():
    """Load the ML-prescreened peptide set from Person A - or placeholder."""
    path = os.path.join(DATA_DIR, "prescreened_peptides.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return PLACEHOLDER_CANDIDATES[["id","sequence","length"]].copy()

def is_placeholder():
    """Returns True if using placeholder data (real docking results not found)."""
    return not os.path.exists(os.path.join(DATA_DIR, "docking_scores.csv"))

def pipeline_status():
    """Returns current pipeline completion status, checked against real file paths."""
    status = {
        "Dataset collected"      : os.path.exists(os.path.join(DATA_DIR, "training_dataset.csv")),
        "ML model trained"       : os.path.exists(os.path.join(DATA_DIR, "prescreened_peptides.csv")),
        "Receptor prepared"      : os.path.exists(os.path.join(DOCKING_DIR, "receptor_af.pdbqt")),
        "Vina config ready"      : os.path.exists(os.path.join(DOCKING_DIR, "vina_bigbox.conf")),
        "Peptides folded"        : os.path.exists(FOLDED_DIR),
        "Docking complete"       : os.path.exists(os.path.join(DATA_DIR, "docking_scores.csv")),
        "Master results merged"  : os.path.exists(os.path.join(DATA_DIR, "master_results.csv")),
        "3D complexes generated" : os.path.exists(COMPLEX_DIR) and
                                     len(os.listdir(COMPLEX_DIR)) > 0,
    }
    return status

def pipeline_stats():
    """
    Real summary numbers for the home page metrics, replacing the
    hardcoded '1,000 designed / 312 screened' placeholders.
    Returns a dict - falls back to None for any stat it can't compute,
    so home.py can show a sensible default instead of a wrong number.
    """
    stats = {
        "total_folded"   : None,
        "ml_screened"    : None,
        "total_docked"   : None,
        "top_candidates" : None,
        "best_dG"        : None,
    }

    prescreened_path = os.path.join(DATA_DIR, "prescreened_peptides.csv")
    if os.path.exists(prescreened_path):
        stats["ml_screened"] = len(pd.read_csv(prescreened_path))

    docking_path = os.path.join(DATA_DIR, "docking_scores.csv")
    if os.path.exists(docking_path):
        df = pd.read_csv(docking_path)
        stats["total_docked"] = len(df)
        stats["top_candidates"] = len(df[df["dG"] <= DG_THRESHOLD])
        stats["best_dG"] = round(df["dG"].min(), 2)

    if os.path.exists(FOLDED_DIR):
        stats["total_folded"] = len([f for f in os.listdir(FOLDED_DIR) if f.endswith(".pdb")])

    return stats