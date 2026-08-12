"""
MDR PepDesign - Batch Ligand Prep + Docking Pipeline (LOCAL WINDOWS VERSION)
==============================================================================
Same validated pipeline as the Colab version: RDKit -> Meeko (rigid) -> Vina.
This is pure Python logic, so it behaves identically on Windows - the only
real differences are the Vina binary path and the absence of apt-get/wget.

PREREQUISITES (run once in your pepdesign conda env):
    pip install numpy scipy          (do NOT use -U/upgrade if it already works)
    pip install meeko rdkit gemmi tqdm

WHAT THIS DOES: identical logic to batch_dock_colab.py - see that file's
docstring for the full explanation. Only paths differ.
"""

import os
import glob
import json
import subprocess
import time

from rdkit import Chem
from meeko import MoleculePreparation, PDBQTWriterLegacy

# ============================================================
# SETTINGS - edit these if your paths/protein change
# ============================================================
PROJECT_ROOT   = r"D:\mdr-pepdesign"
FOLDED_DIR     = "data/folded"
LIGANDS_DIR    = "docking/ligands_clean"
RESULTS_DIR    = "docking/results"
VINA_PATH      = r"D:\mdr-pepdesign\tools\vina_1.2.7_win.exe"   # Windows binary - different from Colab's Linux one
VINA_CONFIG    = "docking/vina_bigbox.conf"
LOG_FILE       = "docking/batch_log.txt"
VINA_CPU       = 2
COOLDOWN_EVERY = 20
COOLDOWN_SECS  = 5
# ============================================================

os.chdir(PROJECT_ROOT)
os.makedirs(LIGANDS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def prepare_ligand(pep_id):
    """PDB -> rigid PDBQT via RDKit + Meeko. Returns (success: bool, message: str)."""
    pdb_path = os.path.join(FOLDED_DIR, f"{pep_id}.pdb")
    out_path = os.path.join(LIGANDS_DIR, f"{pep_id}_rigid.pdbqt")

    if os.path.exists(out_path):
        return True, "already prepared"

    if not os.path.exists(pdb_path):
        return False, "source PDB missing"

    try:
        mol = Chem.MolFromPDBFile(pdb_path, removeHs=False)
        if mol is None:
            return False, "RDKit could not parse PDB (likely aromatic ring ambiguity - HIS/TRP/PHE/TYR)"

        mol_h = Chem.AddHs(mol, addCoords=True)

        mk_prep = MoleculePreparation(
            rigidify_bonds_smarts=["[!#1]~[!#1]"],
            rigidify_bonds_indices=[(0, 1)],
        )
        mol_setups = mk_prep.prepare(mol_h)
        setup = mol_setups[0]

        pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(setup)
        if not is_ok:
            return False, f"meeko write failed: {error_msg}"

        with open(out_path, "w") as f:
            f.write(pdbqt_string)

        return True, "prepared"

    except Exception as e:
        return False, f"exception: {e}"


def dock_ligand(pep_id):
    """Run Vina on a prepared ligand. Returns (success: bool, message: str)."""
    lig_path = os.path.join(LIGANDS_DIR, f"{pep_id}_rigid.pdbqt")
    out_path = os.path.join(RESULTS_DIR, f"{pep_id}_out.pdbqt")
    log_path = os.path.join(RESULTS_DIR, f"{pep_id}_log.txt")

    if os.path.exists(log_path):
        return True, "already docked"

    if not os.path.exists(lig_path):
        return False, "prepared ligand missing"

    result = subprocess.run(
        [VINA_PATH, "--config", VINA_CONFIG, "--ligand", lig_path,
         "--out", out_path, "--cpu", str(VINA_CPU)],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        with open(os.path.join(RESULTS_DIR, f"{pep_id}_error.txt"), "w") as f:
            f.write(result.stderr)
        return False, f"vina failed (code {result.returncode})"

    # NOTE: Vina 1.2.x has no --log flag (removed since 1.1.x). Results are
    # in stdout. This was the bug that caused all 311 original "failures".
    with open(log_path, "w") as f:
        f.write(result.stdout)

    del result
    return True, "docked"


def main():
    pdb_files = sorted(glob.glob(os.path.join(FOLDED_DIR, "*.pdb")))
    pep_ids = [os.path.basename(p).replace(".pdb", "") for p in pdb_files]
    total = len(pep_ids)

    log(f"\n{'='*50}")
    log(f"Batch run started - {total} peptides found in {FOLDED_DIR}")
    log(f"{'='*50}")

    prep_ok, prep_fail = 0, []
    dock_ok, dock_fail = 0, []

    for i, pep_id in enumerate(pep_ids):
        ok, msg = prepare_ligand(pep_id)
        if ok:
            prep_ok += 1
            dock_success, dock_msg = dock_ligand(pep_id)
            if dock_success:
                dock_ok += 1
            else:
                dock_fail.append((pep_id, dock_msg))
                log(f"  DOCK FAIL  {pep_id}: {dock_msg}")
        else:
            prep_fail.append((pep_id, msg))
            log(f"  PREP FAIL  {pep_id}: {msg}")

        if (i + 1) % 10 == 0:
            log(f"Progress: {i+1}/{total}  |  prep_ok={prep_ok}  dock_ok={dock_ok}  "
                f"prep_fail={len(prep_fail)}  dock_fail={len(dock_fail)}")

        if (i + 1) % COOLDOWN_EVERY == 0:
            time.sleep(COOLDOWN_SECS)

    log(f"\n{'='*50}")
    log(f"BATCH COMPLETE")
    log(f"Total peptides       : {total}")
    log(f"Ligand prep success  : {prep_ok}")
    log(f"Ligand prep failed   : {len(prep_fail)}")
    log(f"Docking success      : {dock_ok}")
    log(f"Docking failed       : {len(dock_fail)}")
    log(f"{'='*50}")

    with open("docking/prep_failures.json", "w") as f:
        json.dump(prep_fail, f, indent=2)
    with open("docking/dock_failures.json", "w") as f:
        json.dump(dock_fail, f, indent=2)

    log("Failure details saved to docking/prep_failures.json and docking/dock_failures.json")
    log("Run parse_results.py next to extract binding scores into a CSV.")


if __name__ == "__main__":
    main()
