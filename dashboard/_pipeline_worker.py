"""
_pipeline_worker.py
=====================
The actual work happens here, in a separate OS process launched by
pipeline_runner.start_pipeline_job(). Not meant to be imported - run
directly via subprocess with CLI args.

Implements, for ANY protein, the exact steps validated today for EmrE:
  1. Receptor prep: OpenBabel + Gasteiger charges (Section 3 of PROJECT_SUMMARY.md)
  2. Box auto-sizing: computed from actual ligand dimensions instead of a
     hardcoded 35x30x35 - generalizes the fix from today's "ligand too big
     for box" bug so it doesn't need to be rediscovered per protein
  3. Ligand prep: RDKit parse + meeko rigidify (Section 5) - NOT OpenBabel,
     which corrupts aromatic bond orders
  4. Docking: Vina with the auto-sized box, graceful skip-and-log on failure
     (Section 7/9) - same skip-if-exists resume logic as batch_dock_local.py

This module deliberately duplicates some logic from batch_dock_local.py
rather than importing it, because batch_dock_local.py is hardcoded to
EmrE-specific paths/settings and validated as-is - safer to keep it
untouched and have this be its own generalized sibling, than risk
breaking the working EmrE script by making it import-flexible.
"""

import os
import sys
import json
import glob
import argparse
import subprocess
import traceback

from rdkit import Chem
from meeko import MoleculePreparation, PDBQTWriterLegacy


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--job_id", required=True)
    p.add_argument("--protein_pdb", required=True)
    p.add_argument("--pocket_json", required=True)
    p.add_argument("--folded_dir", required=True)
    p.add_argument("--project_root", required=True)
    p.add_argument("--jobs_dir", required=True)
    p.add_argument("--vina_path", default=None)
    return p.parse_args()


def write_status(jobs_dir, job_id, **kwargs):
    os.makedirs(jobs_dir, exist_ok=True)
    path = os.path.join(jobs_dir, f"{job_id}_status.json")
    status = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                status = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    status.update(kwargs)
    with open(path, "w") as f:
        json.dump(status, f, indent=2)


def append_log(jobs_dir, job_id, message):
    os.makedirs(jobs_dir, exist_ok=True)
    path = os.path.join(jobs_dir, f"{job_id}_status.json")
    status = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                status = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    log = status.get("log", [])
    log.append(message)
    status["log"] = log[-200:]  # cap log length so the status file doesn't grow forever
    with open(path, "w") as f:
        json.dump(status, f, indent=2)


def find_vina_binary(explicit_path):
    """Auto-detect the right Vina binary for this OS if not explicitly given."""
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path
    if sys.platform.startswith("win"):
        candidates = ["tools/vina_1.2.7_win.exe", "tools/vina.exe"]
    else:
        candidates = ["./vina", "tools/vina"]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def prep_receptor(protein_pdb, out_path):
    """
    Same command validated in Section 3 of PROJECT_SUMMARY.md.
    OpenBabel + Gasteiger charges - works generically for any protein
    PDB with full atomic detail (NOT CA-only traces - see the 3B5D
    lesson; this function doesn't detect that case, so a quick atom-count
    sanity check happens in main() before this is called).
    """
    result = subprocess.run([
        "obabel", "-ipdb", protein_pdb, "-opdbqt", "-O", out_path,
        "--addh", "-p", "7.4", "--partialcharge", "gasteiger", "-xr"
    ], capture_output=True, text=True)
    return os.path.exists(out_path), result.stderr


def compute_auto_box(folded_pdb_paths, padding=10.0, sample_size=20):
    """
    Generalizes today's box-sizing fix. Instead of a hardcoded 35x30x35
    (which only happened to work for EmrE's specific peptide set), measure
    actual peptide dimensions from a sample of the real ligand set and
    size the box to comfortably fit the largest one, plus padding.

    This directly encodes the lesson from today: a box smaller than the
    rigid ligand's longest dimension causes OOM/hang failures (Section 4).
    """
    import math
    max_dim = 0.0
    sample = folded_pdb_paths[:sample_size]

    for pdb_path in sample:
        try:
            xs, ys, zs = [], [], []
            with open(pdb_path) as f:
                for line in f:
                    if line.startswith("ATOM"):
                        xs.append(float(line[30:38]))
                        ys.append(float(line[38:46]))
                        zs.append(float(line[46:54]))
            if not xs:
                continue
            dims = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
            max_dim = max(max_dim, max(dims))
        except Exception:
            continue  # one bad file shouldn't abort box sizing

    if max_dim == 0.0:
        max_dim = 25.0  # fallback if measurement failed entirely

    box_size = round(max_dim + padding, 1)
    return box_size, box_size, box_size


def prep_ligand(pdb_path, out_path):
    """Identical logic to batch_dock_local.py's prepare_ligand() - RDKit
    parse + meeko rigidify (Section 5). Returns (success, message)."""
    if os.path.exists(out_path):
        return True, "already prepared"
    if not os.path.exists(pdb_path):
        return False, "source PDB missing"

    try:
        from rdkit import RDLogger
        RDLogger.DisableLog('rdApp.*')

        mol = Chem.MolFromPDBFile(pdb_path, removeHs=False)
        if mol is None:
            return False, "RDKit could not parse PDB (geometry-based bond inference failed)"

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


def dock_ligand(vina_path, config_path, lig_path, out_path, log_path):
    """Identical logic to batch_dock_local.py's dock_ligand()."""
    if os.path.exists(log_path):
        return True, "already docked"
    if not os.path.exists(lig_path):
        return False, "prepared ligand missing"

    result = subprocess.run(
        [vina_path, "--config", config_path, "--ligand", lig_path,
         "--out", out_path, "--cpu", "2"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False, f"vina failed (code {result.returncode})"

    with open(log_path, "w") as f:
        f.write(result.stdout)
    return True, "docked"


def main():
    args = parse_args()
    jobs_dir = args.jobs_dir
    job_id = args.job_id
    os.chdir(args.project_root)

    try:
        write_status(jobs_dir, job_id, stage="checking_receptor", progress=0.02, done=False)

        # Sanity check before doing real work: catch the CA-only-structure
        # problem early (Section 2's "3B5D lesson") instead of discovering
        # it after a long run. A real full-atom structure has roughly
        # 7-9 atoms per residue; a CA-only trace has exactly 1 per residue
        # (one ATOM line per CA, nothing else) - checking the ratio catches
        # this even when total atom count alone wouldn't (e.g. a long
        # CA-only chain can still have 100+ total ATOM lines).
        atom_lines, ca_lines = [], []
        with open(args.protein_pdb) as f:
            for l in f:
                if l.startswith("ATOM"):
                    atom_lines.append(l)
                    if l[12:16].strip() == "CA":
                        ca_lines.append(l)

        atom_count = len(atom_lines)
        ca_ratio = len(ca_lines) / atom_count if atom_count else 1.0

        if atom_count < 50:
            write_status(jobs_dir, job_id, stage="failed", done=True,
                error=f"Protein PDB has only {atom_count} ATOM lines - too small "
                       f"to be a real structure.")
            return
        if ca_ratio > 0.9:
            write_status(jobs_dir, job_id, stage="failed", done=True,
                error=f"Protein PDB appears to be a CA-only trace ({len(ca_lines)}/{atom_count} "
                       f"atoms are CA, {ca_ratio:.0%}) - same issue found with 3B5D today. "
                       f"This structure has no side chains and cannot produce a valid receptor. "
                       f"Try an AlphaFold model instead (see Section 2 of PROJECT_SUMMARY.md).")
            return
        append_log(jobs_dir, job_id,
            f"Receptor structure check passed ({atom_count} atoms, {ca_ratio:.0%} CA ratio)")

        # --- Step 1: receptor prep ---
        write_status(jobs_dir, job_id, stage="receptor_prep", progress=0.05)
        os.makedirs("docking", exist_ok=True)
        receptor_out = "docking/receptor_auto.pdbqt"
        ok, err = prep_receptor(args.protein_pdb, receptor_out)
        if not ok:
            write_status(jobs_dir, job_id, stage="failed", done=True,
                error=f"Receptor prep failed: {err}")
            return
        append_log(jobs_dir, job_id, "Receptor prepared (OpenBabel + Gasteiger charges)")

        # --- Step 2: auto box sizing ---
        write_status(jobs_dir, job_id, stage="box_sizing", progress=0.08)
        folded_files = sorted(glob.glob(os.path.join(args.folded_dir, "*.pdb")))
        if not folded_files:
            write_status(jobs_dir, job_id, stage="failed", done=True,
                error=f"No folded peptide PDBs found in {args.folded_dir}")
            return

        sx, sy, sz = compute_auto_box(folded_files)
        pocket = json.loads(args.pocket_json)
        config_path = "docking/vina_auto.conf"
        with open(config_path, "w") as f:
            f.write(f"""receptor = {receptor_out}
center_x = {pocket['cx']}
center_y = {pocket['cy']}
center_z = {pocket['cz']}
size_x = {sx}
size_y = {sy}
size_z = {sz}
exhaustiveness = 8
num_modes = 9
energy_range = 3
""")
        append_log(jobs_dir, job_id,
            f"Box auto-sized to {sx}x{sy}x{sz} A based on real peptide dimensions")

        # --- Step 3 & 4: ligand prep + docking, per peptide ---
        vina_path = find_vina_binary(args.vina_path)
        if not vina_path:
            write_status(jobs_dir, job_id, stage="failed", done=True,
                error="Vina binary not found - place it in tools/ or pass --vina_path")
            return

        ligands_dir = "docking/ligands_auto"
        results_dir = "docking/results_auto"
        os.makedirs(ligands_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        total = len(folded_files)
        prep_ok, dock_ok, failed = 0, 0, []

        for i, pdb_path in enumerate(folded_files):
            pep_id = os.path.basename(pdb_path).replace(".pdb", "")
            lig_path = os.path.join(ligands_dir, f"{pep_id}_rigid.pdbqt")
            out_path = os.path.join(results_dir, f"{pep_id}_out.pdbqt")
            log_path = os.path.join(results_dir, f"{pep_id}_log.txt")

            ok, msg = prep_ligand(pdb_path, lig_path)
            if ok:
                prep_ok += 1
                d_ok, d_msg = dock_ligand(vina_path, config_path, lig_path, out_path, log_path)
                if d_ok:
                    dock_ok += 1
                else:
                    failed.append((pep_id, d_msg))
            else:
                failed.append((pep_id, msg))

            progress = 0.1 + 0.85 * ((i + 1) / total)
            write_status(jobs_dir, job_id, stage="docking", progress=round(progress, 3),
                prep_ok=prep_ok, dock_ok=dock_ok, failed_count=len(failed), total=total)

            if (i + 1) % 10 == 0:
                append_log(jobs_dir, job_id,
                    f"Progress {i+1}/{total} - prepped {prep_ok}, docked {dock_ok}, failed {len(failed)}")

        # --- Step 5: parse results ---
        write_status(jobs_dir, job_id, stage="parsing_results", progress=0.97)
        import re
        import pandas as pd
        rows = []
        for f in glob.glob(os.path.join(results_dir, "*_log.txt")):
            pid = os.path.basename(f).replace("_log.txt", "")
            with open(f) as fh:
                content = fh.read()
            m = re.search(r'^\s*1\s+(-?\d+\.?\d*)', content, re.MULTILINE)
            if m:
                rows.append({"id": pid, "dG": float(m.group(1))})

        scores_path = f"data/docking_scores_{args.job_id}.csv"
        os.makedirs("data", exist_ok=True)
        if rows:
            df = pd.DataFrame(rows).sort_values("dG")
            df.to_csv(scores_path, index=False)

        write_status(jobs_dir, job_id, stage="complete", progress=1.0, done=True,
            total_peptides=total, prep_ok=prep_ok, dock_ok=dock_ok,
            failed_count=len(failed), scores_csv=scores_path,
            best_dG=float(rows[0]["dG"]) if rows else None,
            failed_detail=failed[:50])  # cap so the status file doesn't balloon
        append_log(jobs_dir, job_id, f"Pipeline complete: {dock_ok}/{total} docked successfully")

    except Exception as e:
        write_status(jobs_dir, job_id, stage="failed", done=True,
            error=f"Unhandled exception: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
