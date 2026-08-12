# MDR-PepDesign: Docking Pipeline Summary
**Project:** AI-assisted peptide inhibitor design against EmrE (multidrug resistance transporter)
**Status as of this summary:** Pipeline validated end-to-end. 282/341 peptides successfully docked.

---

## 1. Project Structure (two-person FYP team)

- **Person A**: AMP-likeness ML classifier + ESMFold peptide structure prediction
- **Person B (you)**: Receptor preparation + molecular docking + results pipeline
- Local project root: `D:\mdr-pepdesign\`
- Cloud working copy: Google Drive `MyDrive/mdr-pepdesign/` (mirrors local structure)

---

## 2. Target Protein: EmrE

**Initial problem (do not repeat):** The original target structure, PDB entry **3B5D**, was found to be a **C-alpha-only trace** (199 atoms total, backbone only, no side chains) — a known limitation of this specific deposited structure at 3.8 Å resolution. This is NOT a bug in any cleaning script; it is the actual deposited data. **Do not attempt to dock against 3B5D or any receptor derived from it.**

**Fix:** Switched to an **AlphaFold model** instead.
- UniProt ID: **P23895**
- Downloaded via AlphaFold API: `https://alphafold.ebi.ac.uk/api/prediction/P23895` (returns current `pdbUrl`; do not hardcode version-numbered URLs like `AF-P23895-F1-model_v4.pdb` as the version suffix changes)
- 110 residues, mean pLDDT confidence ~75.8 (acceptable for a membrane protein)
- Saved as: `data/emre_alphafold.pdb`

---

## 3. Receptor Preparation (VALIDATED — do not change)

**File:** `docking/receptor_af.pdbqt`

**Tool:** OpenBabel (NOT MGLTools — MGLTools failed entirely with `AssertionError: assert len(molecule.allAtoms.bonds[0])` on the old CA-only structure; never retried on the AlphaFold structure since OpenBabel already worked)

**Exact command:**
```bash
obabel -ipdb data/emre_alphafold.pdb -opdbqt -O docking/receptor_af.pdbqt \
  --addh -p 7.4 --partialcharge gasteiger -xr
```

**Validation performed:** Confirmed nonzero, varied Gasteiger partial charges per atom (e.g. N: -0.123, CA: +0.170, O: -0.272) and correct AutoDock atom types (N, C, OA, S). The `-xr` flag marks it as rigid (confirmed zero `ROOT`/`BRANCH`/`TORSDOF` keywords — correct for a receptor).

**Known harmless warning:** `Failed to kekulize aromatic bonds` — appears due to TRP/PHE/HIS residues; does not affect the final charge/type assignment for the receptor (this same warning DOES cause real problems for ligand prep — see Section 5).

---

## 4. Docking Box / Binding Site

**File:** `docking/vina_bigbox.conf`

```
receptor = docking/receptor_af.pdbqt
center_x = -5.282
center_y = 6.619
center_z = -0.313
size_x = 35
size_y = 30
size_z = 35
exhaustiveness = 8
num_modes = 9
energy_range = 3
```

**Important history:** An earlier, smaller box (20×20×20, center same) caused every single docking run to either hang indefinitely or get OOM-killed (`anon-rss` climbing to ~11.8GB before kernel SIGKILL). Root cause: **rigid peptide ligands (~30 Å longest dimension) physically could not fit inside a 20 Å box**, causing Vina's search to thrash on clashing poses. The 35×30×35 box resolved this completely. Vina will print `WARNING: Search space volume is greater than 27000 Angstrom^3` — this is expected and acceptable for peptide-protein docking (unlike typical small-molecule pocket docking), should be mentioned as a methodological note in the paper.

**Coordinates were re-derived for the AlphaFold structure specifically** (not reused from the original 3B5D-frame coordinates, which would have been wrong since AlphaFold predictions are not in the same coordinate frame as the original crystal structure).

---

## 5. Ligand Preparation (VALIDATED — the hardest-won part of this pipeline)

**Input:** `data/folded/pep_XXXX.pdb` — ESMFold-predicted structures from Person A (script: calls `https://api.esmatlas.com/foldSequence/v1/pdb/`, clean and reliable, never the source of any bug found today)

**Output:** `docking/ligands_clean/pep_XXXX_rigid.pdbqt`

### Failed approaches (documented so they are not retried)
1. **OpenBabel for ligands** (`obabel -ipdb ... -osdf -h` then meeko) — produces **chemically corrupted bond orders** specifically around aromatic residues (TRP, HIS). Confirmed via SMILES inspection: backbone pattern broke from correct `NC(=O)` repeats into nonsensical `N[C@H](O)` fragments. This was the root cause of the original "71 active torsions" and subsequent garbage docking scores (positive ΔG values, e.g. +46.889 kcal/mol, mean +6,061,302 kcal/mol across a batch) — **NOT a memory bug, a chemistry bug**, since Vina was scoring a non-physical molecule.
2. **MGLTools (`prepare_ligand4.py`)** — never successfully tested on ligands; failed on the receptor side first due to the CA-only 3B5D issue and the path was abandoned before retrying on the corrected receptor.
3. **A custom hand-written PDB→PDBQT Python script** (written in an earlier, separate Claude session) — hardcoded `0.000` charge for every atom, no real torsion tree logic. Do not reuse.
4. **Meeko CLI (`mk_prepare_ligand.py -i file.sdf`)** — works, but requires SDF input (does not accept PDB directly in the installed version), and inherits OpenBabel's bond-order corruption if OpenBabel was used to make the SDF.
5. **Meeko's `Polymer.from_pdb_string()` / `Polymer.from_pdb_file()` Python API** — broken/inconsistent across meeko versions during testing (`TypeError`, then `AttributeError`); abandoned in favor of the RDKit-based approach below.

### Working approach (final, validated)
**RDKit's native PDB parser** (not OpenBabel) correctly infers bond orders, including aromatic rings, in the large majority of cases:

```python
from rdkit import Chem
from meeko import MoleculePreparation, PDBQTWriterLegacy

mol = Chem.MolFromPDBFile(pdb_path, removeHs=False)
mol_h = Chem.AddHs(mol, addCoords=True)

mk_prep = MoleculePreparation(
    rigidify_bonds_smarts=["[!#1]~[!#1]"],   # matches all heavy-atom bonds
    rigidify_bonds_indices=[(0, 1)],
)
mol_setups = mk_prep.prepare(mol_h)
setup = mol_setups[0]
pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(setup)
```

This produces a **fully rigid ligand** (`TORSDOF 0`) — internal flexibility is intentionally disabled. This was a deliberate methodological choice (see Section 6), not a limitation we were forced into — it works correctly once paired with the larger box (Section 4).

### Known, expected failure mode (~13% of peptides)
RDKit's `MolFromPDBFile` infers bonds from 3D geometry alone (no true chemical templates). For roughly 13% of peptides (45/341 in this run), this produces an invalid valence (e.g. `Explicit valence for atom # 42 C, 5, is greater than permitted` or oxygen with valence 3-4 instead of 2). Pattern observed: failures correlate with aromatic residues (HIS, TRP, PHE, TYR) in compact/folded geometries where backbone or ring atoms sit close enough in 3D space for RDKit's proximity-based bond guesser to misassign connectivity. **This is a known limitation of geometry-only PDB parsing, not a bug in our pipeline** — worth stating explicitly in the paper's methods/limitations section. Untested potential fix for future work: `Chem.MolFromPDBFile(path, proximityBonding=False)`.

---

## 6. Methodological Choice: Rigid Ligand Docking

**Decision:** All peptide ligands are docked as **fully rigid bodies** (`TORSDOF 0`), using their ESMFold-predicted fold as-is. Vina searches only translation + rotation (6 degrees of freedom), not internal conformational flexibility.

**Justification for the paper:** This is standard practice for **large-scale peptide screening** (as opposed to detailed pose refinement of a small number of final candidates). Full backbone+sidechain flexibility for a ~20-residue peptide creates a combinatorially large search space (we measured 56-71 active torsions with full flexibility) that is both computationally prohibitive at scale and arguably unnecessary at the screening stage, since the peptide's fold is already determined by ESMFold. This mirrors a common two-stage approach in peptide drug discovery: rigid/coarse screening of a large candidate pool, followed by flexible refinement of only the top hits.

**Caveat to disclose:** Because the ligand cannot adapt its conformation to the pocket, binding affinities here represent how well the ESMFold-predicted fold fits the pocket, not the true minimum-energy bound conformation. Top candidates should ideally be re-docked with flexible sidechains (or full MD refinement) as a follow-up validation step before any experimental work.

---

## 7. Batch Docking Scripts

Three scripts, identical core logic (RDKit parse → meeko rigidify → Vina dock), different environments:

- **`setup_colab.py`** — one-time Colab environment setup (Vina Linux binary download, OpenBabel via apt, Python deps). Must be re-run after every Colab runtime restart (packages/files don't persist).
- **`batch_dock_colab.py`** — Colab batch runner. **Reads/writes to Google Drive** (`/content/drive/MyDrive/mdr-pepdesign/...`), not Colab's temporary local disk, so progress survives session disconnects. Has skip-if-exists logic at both the ligand-prep and docking stages (safe to stop/resume anytime).
- **`batch_dock_local.py`** — identical logic for local Windows/Jupyter execution. Uses `D:\mdr-pepdesign\tools\vina_1.2.7_win.exe` (Windows binary — NOT interchangeable with the Linux binary used on Colab, must download separately per-platform).
- **`parse_results.py`** — parses Vina's stdout-captured `_log.txt` files (NOT a `--log` CLI flag — see Section 8) into `docking_scores.csv` / `top_candidates.csv`.

**Critical bug fixed in the Vina config:** the `receptor = ...` path inside `vina_bigbox.conf` must be an **absolute path** when running batch jobs from Drive-mounted Colab (`/content/drive/MyDrive/mdr-pepdesign/docking/receptor_af.pdbqt`), not a relative path — a relative path silently resolved against Colab's local working directory instead of Drive, causing 188 of 296 prepared ligands to fail docking with `could not open "docking/receptor_af.pdbqt" for reading` partway through a batch run. Always verify the config's receptor path matches the actual execution environment.

---

## 8. Other Resolved Bugs (for completeness / paper's limitations section)

- **Vina 1.2.x has no `--log` CLI flag** (removed since 1.1.x; only `--out`, `--dir`, `--write_maps` exist for output). Original scripts assumed `--log` existed, causing every single docking call to fail instantly with a CLI parse error (0 real dockings, despite a misleading "311 failed, 0 succeeded" summary). Fix: capture `subprocess.run(...).stdout` directly and write it to the log file in Python.
- **Windows SSL certificate store corruption** caused local Jupyter to fail to launch entirely (`ssl.SSLError: [ASN1: NOT_ENOUGH_DATA]`, traced via `dmesg`-equivalent diagnosis to a malformed Windows cert store entry). Worked around via a `sitecustomize.py` patch in the `pepdesign` conda env that catches and ignores `ssl.SSLError` during `load_default_certs()`. Does not affect HTTPS verification for `requests`-based API calls (which use `certifi`, a separate code path).
- **numpy/scipy version mismatch** when force-upgrading (`pip install -U numpy scipy meeko ...` together) breaks scipy's internal compatibility check (`AttributeError: module 'numpy._core._multiarray_umath' has no attribute '_blas_supports_fpe'`). Fix: install numpy/scipy without the `-U` flag, let Colab's/conda's pre-existing compatible versions stand, then install meeko's other dependencies on top.

---

## 9. Current Results

- **Total peptides attempted:** 341 (all of Person A's successfully-folded ESMFold structures)
- **Ligand prep success:** 296/341 (87%)
- **Docking success:** 282/341 (83%)
- **Score range:** best ΔG = -12.10 kcal/mol, mean = -5.34 kcal/mol
- **Files:**
  - `data/docking_scores.csv` — all 282 scored peptides
  - `data/top_candidates.csv` — peptides with ΔG ≤ -8.0 kcal/mol (180 peptides at this threshold; consider tightening to -9.0 or -10.0 for a more selective final shortlist)
  - `data/master_results.csv` — docking scores merged with Person A's ML classifier scores (`prescreened_peptides.csv`). Note: 311 peptides passed ML pre-screening but the full 341-peptide set was docked (broader net), so 21/282 docked peptides have no corresponding ML score, and 50/311 ML-approved peptides were never successfully docked (structure/docking failures).
  - `docking/prep_failures.json`, `docking/dock_failures.json` — itemized failure reasons per peptide ID

---

## 10. Suggested Next Steps

1. Investigate whether ML-approved peptides score better on docking than ML-rejected ones (validation check for Person A's classifier — quick pandas groupby on `master_results.csv`).
2. Decide on final shortlist threshold for top candidates (currently 180 at -8.0 kcal/mol — likely too permissive for a "final shortlist" narrative).
3. Consider flexible re-docking of only the top N candidates as a refinement/validation step.
4. Build the Streamlit dashboard (per original project plan) to visualize `master_results.csv`.
5. For future protein targets: confirm the chosen PDB/AlphaFold structure has full side-chain atoms before any prep work (the CA-only 3B5D issue cost significant time before being caught) — quick check: `len([l for l in open(pdb_file) if l.startswith('ATOM')])` should be roughly 7-9× the residue count for a normal full-atom structure, not roughly 1×.
