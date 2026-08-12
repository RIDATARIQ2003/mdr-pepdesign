# dashboard/input_layer.py
# Complete engine — no manual steps, no external websites

import requests, subprocess, re, os, json
import pandas as pd

# tool_setup.py (fpocket build + P2Rank download bootstrap) is optional —
# it's only needed for the Streamlit Cloud deployment path, not for local
# testing or for Method 4 (the membrane heuristic), which has zero
# external dependencies. Import defensively so the whole file still
# works locally even if tool_setup.py hasn't been added yet.
try:
    from tool_setup import ensure_fpocket_installed, ensure_p2rank_installed
except ImportError:
    ensure_fpocket_installed = None
    ensure_p2rank_installed = None

# ── CONSTANTS FOR METHOD 4 (membrane burial heuristic) ────────────

# Kyte-Doolittle hydrophobicity scale — standard values used to predict
# transmembrane helices from sequence alone. Higher = more hydrophobic.
KD_SCALE = {
    'A': 1.8,  'R': -4.5, 'N': -3.5, 'D': -3.5, 'C': 2.5,
    'Q': -3.5, 'E': -3.5, 'G': -0.4, 'H': -3.2, 'I': 4.5,
    'L': 3.8,  'K': -3.9, 'M': 1.9,  'F': 2.8,  'P': -1.6,
    'S': -0.8, 'T': -0.7, 'W': -0.9, 'Y': -1.3, 'V': 4.2
}

THREE_TO_ONE = {
    'ALA': 'A', 'ARG': 'R', 'ASN': 'N', 'ASP': 'D', 'CYS': 'C',
    'GLN': 'Q', 'GLU': 'E', 'GLY': 'G', 'HIS': 'H', 'ILE': 'I',
    'LEU': 'L', 'LYS': 'K', 'MET': 'M', 'PHE': 'F', 'PRO': 'P',
    'SER': 'S', 'THR': 'T', 'TRP': 'W', 'TYR': 'Y', 'VAL': 'V'
}

# Charged residues are a much stronger anomaly signal inside a membrane
# than merely polar ones — a buried charge almost always means something
# functionally important (proton/ion binding, gating, catalysis).
# NOTE: Cysteine is deliberately excluded from POLAR. Buried Cys is very
# common in ANY protein (disulfide bonds, tight structural core packing)
# and is NOT a reliable signal of a membrane functional site on its own —
# testing on EmrE showed it out-scoring the real site (E14) purely from
# local packing density, which is a false positive.
CHARGED = set('DEKRH')
POLAR   = set('STNQY')


# ── MAIN FUNCTIONS ───────────────────────────────────────────────

def resolve_structure(user_input: str) -> str:
    """
    Takes PDB ID or FASTA sequence.
    Returns clean PDB string ready for docking.
    """
    user_input = user_input.strip()
    if user_input.startswith('>') or _is_sequence(user_input):
        print("Input detected as FASTA — folding with ESMFold...")
        return _fold_with_esmfold(user_input)
    else:
        print(f"Input detected as PDB ID — fetching {user_input}...")
        return _fetch_and_clean_pdb(user_input.upper())


def detect_pocket(pdb_file, known_residue=None, known_chains=None):
    """
    4-method pocket detection engine.
    Method 1: Known residue (most accurate — use when residue is known)
    Method 2: fpocket (works for soluble proteins)
    Method 3: P2Rank (general ML pocket predictor — soluble-protein bias)
    Method 4: Membrane burial heuristic (fpocket/P2Rank blind spot —
              finds buried polar/charged residues inside predicted TM
              helices, e.g. E14-style sites in transporters)

    Parameters:
    -----------
    pdb_file       : str  — path to clean PDB file
    known_residue  : int  — residue number if known (e.g. 14 for EmrE)
    known_chains   : list — chain letters (e.g. ['A','B'] for EmrE)
    """

    # METHOD 1 — Known residue
    if known_residue is not None:
        print(f"[Method 1] Extracting coords from residue {known_residue}...")
        coords = _coords_from_residue(pdb_file, known_residue,
                                       known_chains or ['A'])
        if coords:
            coords['method'] = f'residue_{known_residue}'
            print(f"  ✅ Success")
            return coords
        print(f"  ❌ Residue {known_residue} not found in PDB")

    # METHOD 2 — fpocket
    print("[Method 2] Trying fpocket...")
    coords = _try_fpocket(pdb_file)
    if coords:
        coords['method'] = 'fpocket'
        print(f"  ✅ fpocket found a pocket")
        return coords
    print(f"  ❌ fpocket found no pockets")

    # METHOD 3 — P2Rank
    print("[Method 3] Trying P2Rank...")
    coords = _try_p2rank(pdb_file)
    if coords:
        coords['method'] = 'p2rank'
        print(f"  ✅ P2Rank found a pocket")
        return coords
    print(f"  ❌ P2Rank also failed")

    # METHOD 4 — Membrane burial heuristic (the actual fix for EmrE-like targets)
    print("[Method 4] Trying membrane burial heuristic...")
    coords = _try_membrane_heuristic(pdb_file)
    if coords:
        coords['method'] = 'membrane_burial_heuristic'
        print(f"  ✅ Membrane heuristic found a candidate site: "
              f"{coords.get('residue_hint', '?')}")
        return coords
    print(f"  ❌ Membrane heuristic also failed")

    print("\n❌ All methods failed — ask user to enter coordinates manually")
    return None


# ── PRIVATE FUNCTIONS ────────────────────────────────────────────

def _is_sequence(s):
    aa = set("ACDEFGHIKLMNPQRSTVWY")
    return len(s) > 10 and set(s.upper()).issubset(aa | {'\n', ' '})


def _fetch_and_clean_pdb(pdb_id):
    """Fetch from RCSB and clean — removes HETATM, waters, ligands."""
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    r   = requests.get(url, timeout=30)
    r.raise_for_status()
    lines = [l for l in r.text.split('\n')
             if l.startswith(('ATOM','TER','END'))]
    return '\n'.join(lines)


def _fold_with_esmfold(sequence):
    """Fold a FASTA sequence using ESMFold API."""
    seq = sequence.strip()
    if seq.startswith('>'):
        seq = '\n'.join(seq.split('\n')[1:])
    seq = seq.replace('\n', '').strip()
    r = requests.post(
        "https://api.esmatlas.com/foldSequence/v1/pdb/",
        data=seq,
        headers={"Content-Type": "text/plain"},
        timeout=120)
    r.raise_for_status()
    # Clean the folded structure too
    lines = [l for l in r.text.split('\n')
             if l.startswith(('ATOM','TER','END'))]
    return '\n'.join(lines)


def _coords_from_residue(pdb_file, residue_num, chains):
    """Extract centroid of a specific residue across specified chains."""
    coords = []
    try:
        with open(pdb_file) as f:
            for line in f:
                if not line.startswith('ATOM'): continue
                res   = int(line[22:26].strip())
                chain = line[21].strip()
                if res == residue_num and chain in chains:
                    coords.append((
                        float(line[30:38]),
                        float(line[38:46]),
                        float(line[46:54])
                    ))
        if not coords: return None
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        cz = sum(c[2] for c in coords) / len(coords)
        return {"cx":round(cx,3), "cy":round(cy,3),
                "cz":round(cz,3), "volume":300.0}
    except Exception as e:
        print(f"  Error: {e}")
        return None


def _try_fpocket(pdb_file):
    """Run fpocket and return top pocket centroid."""
    try:
        fpocket_bin = ensure_fpocket_installed()
        if not fpocket_bin:
            print("  fpocket unavailable (build failed or no compiler — "
                  "expected on plain Windows) — skipping")
            return None
        subprocess.run([fpocket_bin, '-f', pdb_file],
            capture_output=True, text=True, timeout=60)
        out_dir   = pdb_file.replace('.pdb', '_out')
        info_file = os.path.join(out_dir, 'pockets', 'pocket1_info.txt')
        if not os.path.exists(info_file):
            print("  fpocket ran but produced no pocket1_info.txt "
                  "(likely zero pockets found — normal for membrane proteins)")
            return None
        with open(info_file) as f:
            content = f.read()
        cx  = float(re.search(r'Cent. coor x.*?(\S+)', content).group(1))
        cy  = float(re.search(r'Cent. coor y.*?(\S+)', content).group(1))
        cz  = float(re.search(r'Cent. coor z.*?(\S+)', content).group(1))
        vol = float(re.search(r'Volume.*?(\S+)',        content).group(1))
        return {"cx":round(cx,3), "cy":round(cy,3),
                "cz":round(cz,3), "volume":round(vol,1)}
    # FIX: was a bare `except:` before — that silently swallowed EVERY
    # possible failure (fpocket not installed, binary crash, timeout,
    # permissions, etc.) and made it indistinguishable from "fpocket ran
    # fine and legitimately found nothing." This is very likely why it
    # was unclear whether fpocket or the environment itself was the
    # problem. Now every failure path prints its actual reason.
    except FileNotFoundError:
        print("  fpocket error: binary not found — is fpocket installed and on PATH?")
        return None
    except subprocess.TimeoutExpired:
        print("  fpocket error: timed out after 60s")
        return None
    except Exception as e:
        print(f"  fpocket error: {type(e).__name__}: {e}")
        return None


def _try_p2rank(pdb_file):
    """Run P2Rank ML pocket predictor."""
    try:
        p2rank_bin = ensure_p2rank_installed()
        if not p2rank_bin:
            print("  P2Rank unavailable (download/setup failed) — skipping")
            return None
        subprocess.run(
            [p2rank_bin, 'predict', '-f', pdb_file, '-o', 'p2rank_output'],
            capture_output=True, text=True, timeout=120)
        base      = os.path.basename(pdb_file).replace('.pdb', '')
        pred_file = os.path.join('p2rank_output', f'{base}_predictions.csv')
        if not os.path.exists(pred_file): return None
        df = pd.read_csv(pred_file)
        df.columns = df.columns.str.strip()
        if df.empty: return None
        top = df.iloc[0]
        return {
            "cx"    : round(float(top['center_x']), 3),
            "cy"    : round(float(top['center_y']), 3),
            "cz"    : round(float(top['center_z']), 3),
            "volume": round(float(top['score']),    1)
        }
    except Exception as e:
        print(f"  P2Rank error: {e}")
        return None


# ── METHOD 4: MEMBRANE BURIAL HEURISTIC ──────────────────────────
# This is the actual fix for EmrE-style targets. fpocket looks for
# enclosed solvent cavities; P2Rank is a general ML predictor trained
# mostly on soluble proteins. Neither is built to find a site like E14 —
# a polar/charged residue sitting INSIDE a hydrophobic membrane-spanning
# helix. That combination is structurally rare precisely because it's
# usually functionally important (proton/ion binding, gating), which is
# the same reasoning a person uses to spot such a site manually. This
# automates that reasoning instead of guessing at cavity geometry.

def _parse_residues(pdb_file):
    """Parse ATOM lines into {chain: {resnum: {'resname':..., 'atoms':[(x,y,z),...]}}}"""
    chains = {}
    with open(pdb_file) as f:
        for line in f:
            if not line.startswith('ATOM'):
                continue
            chain   = line[21].strip() or 'A'
            resnum  = int(line[22:26])
            resname = line[17:20].strip()
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            chains.setdefault(chain, {}).setdefault(
                resnum, {'resname': resname, 'atoms': []})
            chains[chain][resnum]['atoms'].append((x, y, z))
    return chains


def _kd_tm_regions(seq, window=19, threshold=1.3):
    """
    Predicts transmembrane helix positions from sequence using a sliding
    Kyte-Doolittle hydrophobicity window. window=19 is the standard
    default (a real TM helix is ~19-23 residues to span a bilayer).

    threshold=1.3, not the textbook 1.6: validated against EmrE
    (diagnose_tm_detection.py) — at 1.6, only 14.5% of the sequence was
    flagged as TM and the known functional site (E14) was excluded by a
    0.226 shortfall. This isn't a quirk of EmrE specifically: transporter
    proteins need polar/charged residues INSIDE their TM helices to form
    a functional channel, so their average per-window hydrophobicity is
    genuinely lower than single-pass/structural membrane proteins that
    the standard 1.6 threshold is usually calibrated against. 1.3 is the
    threshold where E14 first passes while still keeping TM coverage at
    a plausible 30% of the sequence (not e.g. 58% at threshold=1.0,
    which would stop meaningfully filtering anything).
    """
    tm_positions = set()
    n = len(seq)
    half = window // 2
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        window_seq = seq[lo:hi]
        if not window_seq:
            continue
        avg = sum(KD_SCALE.get(a, 0.0) for a in window_seq) / len(window_seq)
        if avg >= threshold:
            tm_positions.add(i)
    return tm_positions


def _burial_score(target_atoms, all_atoms, radius=8.0):
    """
    Rough burial proxy (no external dependency required): counts heavy
    atoms within `radius` Angstroms of this residue's centroid. A residue
    surrounded by many nearby atoms is packed into the structure's
    interior (buried); a residue with few neighbors nearby is exposed
    at the surface. Higher score = more buried.
    """
    cx = sum(a[0] for a in target_atoms) / len(target_atoms)
    cy = sum(a[1] for a in target_atoms) / len(target_atoms)
    cz = sum(a[2] for a in target_atoms) / len(target_atoms)
    count = 0
    r2 = radius * radius
    for (x, y, z) in all_atoms:
        d2 = (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2
        if 0 < d2 <= r2:
            count += 1
    return count, (cx, cy, cz)


def _candidates_at_threshold(chains, all_atoms, threshold):
    """Builds the candidate list at one specific TM-detection threshold."""
    candidates = []
    for chain_id, residues in chains.items():
        resnums = sorted(residues.keys())
        seq = ''.join(THREE_TO_ONE.get(residues[r]['resname'], 'X')
                      for r in resnums)
        tm_positions = _kd_tm_regions(seq, threshold=threshold)

        for idx, resnum in enumerate(resnums):
            if idx not in tm_positions:
                continue
            aa = seq[idx]
            if aa not in CHARGED and aa not in POLAR:
                continue

            atoms = residues[resnum]['atoms']
            burial, centroid = _burial_score(atoms, all_atoms)

            candidates.append({
                'chain': chain_id, 'resnum': resnum, 'aa': aa,
                'charged': aa in CHARGED,
                'score': burial, 'centroid': centroid
            })
    return candidates


def _try_membrane_heuristic(pdb_file):
    """
    Method 4 — for membrane proteins where fpocket/P2Rank both fail.

    Uses an ADAPTIVE threshold, not one fixed number. threshold=1.3 was
    what EmrE specifically needed (see diagnose_tm_detection.py) — but
    hardcoding that as a universal default would mean overfitting every
    future protein to one calibration example. Instead this starts at
    the textbook-standard threshold (1.6) and progressively loosens it
    in steps of 0.1 down to a floor of 1.0 (below which TM coverage
    stops meaningfully filtering the sequence — validated at ~58%
    coverage on EmrE, too broad to be a useful "unusual residue"
    signal). It stops at the FIRST threshold, strictest to loosest,
    where a buried charged residue actually appears — so each protein
    finds its own appropriate strictness within this bounded, documented
    range instead of all being forced through EmrE's specific number.
    """
    try:
        chains = _parse_residues(pdb_file)
        if not chains:
            return None

        all_atoms = [a for res in chains.values()
                       for r in res.values()
                       for a in r['atoms']]

        THRESHOLD_RANGE = [1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0]  # strict → loose

        candidates = []
        used_threshold = THRESHOLD_RANGE[-1]
        for threshold in THRESHOLD_RANGE:
            candidates = _candidates_at_threshold(chains, all_atoms, threshold)
            if any(c['charged'] for c in candidates):
                used_threshold = threshold
                break

        if not candidates:
            return None

        candidates.sort(key=lambda c: c['score'], reverse=True)

        print(f"  TM threshold used: {used_threshold} "
              f"(searched {THRESHOLD_RANGE[0]}→{THRESHOLD_RANGE[-1]}, "
              f"stopped at first threshold with a charged candidate)")
        print("  Top candidates (any residue type):")
        for c in candidates[:5]:
            tag = "charged" if c['charged'] else "polar"
            print(f"    {c['aa']}{c['resnum']} (chain {c['chain']}) "
                  f"[{tag}] score={c['score']:.1f}")

        charged_candidates = [c for c in candidates if c['charged']]
        pool = charged_candidates if charged_candidates else candidates
        if charged_candidates:
            print(f"  Using charged-residue tier "
                  f"({len(charged_candidates)} candidate(s) found)")
        else:
            print("  No charged residues found even at loosest threshold — "
                  "falling back to polar tier")

        best = pool[0]

        # If the same residue number scores highly on multiple chains
        # (classic case: a homodimer interface site like E14 on both
        # chain A and chain B), average across all matching chains
        # instead of only the single highest-scoring one.
        matching = [c for c in pool[:10] if c['resnum'] == best['resnum']]
        cx = sum(c['centroid'][0] for c in matching) / len(matching)
        cy = sum(c['centroid'][1] for c in matching) / len(matching)
        cz = sum(c['centroid'][2] for c in matching) / len(matching)

        print(f"  Best candidate: {best['aa']}{best['resnum']} "
              f"(found on {len(matching)} chain(s), score {best['score']:.1f})")

        return {
            "cx": round(cx, 3), "cy": round(cy, 3), "cz": round(cz, 3),
            "volume": round(best['score'], 1),
            "residue_hint": f"{best['aa']}{best['resnum']}",
            "tm_threshold_used": used_threshold
        }

    except Exception as e:
        print(f"  Membrane heuristic error: {type(e).__name__}: {e}")
        return None