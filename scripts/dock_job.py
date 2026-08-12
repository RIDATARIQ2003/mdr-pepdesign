"""
scripts/dock_job.py
=====================
Runs INSIDE GitHub Actions, not on your machine. Reads job input files
that the dashboard already pushed into the repo, runs the same
validated RDKit + Meeko (rigid) + Vina pipeline as batch_dock_local.py,
and writes results back into the same job folder so the dashboard can
read them via the GitHub API afterwards.

Reads from:   jobs/{job_id}/receptor.pdbqt
              jobs/{job_id}/vina_config.txt
              jobs/{job_id}/ligands/*.pdb
Writes to:    jobs/{job_id}/results/status.json   (polled by dashboard)
              jobs/{job_id}/results/docking_scores.csv
"""

import os
import sys
import glob
import json
import subprocess
import re
import csv
from datetime import datetime

from rdkit import Chem
from meeko import MoleculePreparation, PDBQTWriterLegacy

VINA_BIN = "/usr/local/bin/vina"


def write_status(results_dir, **kwargs):
    """Merge-update status.json so the dashboard can poll live progress."""
    path = os.path.join(results_dir, "status.json")
    status = {}
    if os.path.exists(path):
        with open(path) as f:
            status = json.load(f)
    status.update(kwargs)
    status["updated_at"] = datetime.utcnow().isoformat()
    with open(path, "w") as f:
        json.dump(status, f, indent=2)


def prepare_ligand(pdb_path, out_path):
    """Identical logic to batch_dock_local.py's prepare_ligand()."""
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


def dock_ligand(config_path, lig_path, out_path):
    """Identical logic to batch_dock_local.py's dock_ligand(), including
    the fix for Vina 1.2.x having no --log flag (score parsed from stdout)."""
    result = subprocess.run(
        [VINA_BIN, "--config", config_path, "--ligand", lig_path,
         "--out", out_path, "--cpu", "2"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False, None, f"vina failed (code {result.returncode})"

    match = re.search(r'\s+1\s+([-\d.]+)', result.stdout)
    if not match:
        return False, None, "docked but could not parse score from stdout"
    return True, float(match.group(1)), "ok"


def main():
    job_id = sys.argv[1]
    job_dir = os.path.join("jobs", job_id)
    results_dir = os.path.join(job_dir, "results")
    os.makedirs(results_dir, exist_ok=True)

    write_status(results_dir, stage="starting", done=False, error=None)

    receptor_path = os.path.join(job_dir, "receptor.pdbqt")
    config_path = os.path.join(job_dir, "vina_config.txt")
    ligands_dir = os.path.join(job_dir, "ligands")

    if not (os.path.exists(receptor_path) and os.path.exists(config_path)
            and os.path.isdir(ligands_dir)):
        write_status(results_dir, stage="failed", done=True,
                     error="Missing receptor.pdbqt, vina_config.txt, or ligands/ folder — "
                           "check the dashboard actually pushed all three before triggering")
        return

    ligand_files = sorted(glob.glob(os.path.join(ligands_dir, "*.pdb")))
    total = len(ligand_files)
    write_status(results_dir, stage="docking", done=False, total=total, processed=0)

    rows = []
    for i, pdb_path in enumerate(ligand_files):
        pep_id = os.path.basename(pdb_path).replace(".pdb", "")
        lig_path = os.path.join(results_dir, f"{pep_id}_rigid.pdbqt")
        out_path = os.path.join(results_dir, f"{pep_id}_out.pdbqt")

        ok, msg = prepare_ligand(pdb_path, lig_path)
        if not ok:
            rows.append({"id": pep_id, "dG": "", "status": "failed", "message": msg})
        else:
            dock_ok, dg, dock_msg = dock_ligand(config_path, lig_path, out_path)
            rows.append({
                "id": pep_id,
                "dG": dg if dock_ok else "",
                "status": "docked" if dock_ok else "failed",
                "message": dock_msg
            })

        if (i + 1) % 5 == 0 or (i + 1) == total:
            write_status(results_dir, stage="docking", done=False,
                         total=total, processed=i + 1)

    csv_path = os.path.join(results_dir, "docking_scores.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "dG", "status", "message"])
        writer.writeheader()
        writer.writerows(rows)

    docked_count = sum(1 for r in rows if r["status"] == "docked")
    write_status(results_dir, stage="complete", done=True,
                 total=total, docked=docked_count, failed=total - docked_count)


if __name__ == "__main__":
    main()
