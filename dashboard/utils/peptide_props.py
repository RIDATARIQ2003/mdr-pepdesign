# utils/peptide_props.py
# Computes real physicochemical properties for a peptide sequence on the
# fly, using the exact same BioPython calls Person A's filter script and
# data.py's ML pre-screening step already use (Bio.SeqUtils.ProtParam).
#
# This deliberately does NOT read charge/hydrophobicity/etc from any CSV,
# because master_results.csv only has id, dG, sequence, length, ml_score
# (confirmed in results.py / library.py) - no physicochemical columns
# exist in the real pipeline output. Computing straight from the sequence
# keeps every number shown in the peptide detail view real, not a
# placeholder guess.

from Bio.SeqUtils.ProtParam import ProteinAnalysis

# Normalization ranges pulled directly from Person A's mandatory filter
# thresholds (see fyp_reference_sheet.html / personA_reference_sheet.html,
# Step 07 - filter_peptides.py) so the radar chart's 0-1 scale means
# "how centered in the accepted range" rather than an arbitrary scale.
# Aromaticity/helix don't have a hard filter threshold in the pipeline,
# so those two use an observed-range approximation instead - noted below.
RANGES = {
    "molecular_weight": (500, 2500),   # hard filter range
    "net_charge":       (-1, 5),       # hard filter range
    "gravy":             (-2.0, 1.0),  # hard filter range (hydrophobicity)
    "instability":        (0, 40),     # hard filter ceiling (lower = better)
    "aromaticity":         (0.0, 0.35),  # observed peptide range, not a hard filter
    "helix_fraction":       (0.0, 1.0),  # 0-1 by definition
}

RADAR_AXES = ["Charge", "Hydrophobicity", "Stability",
              "Aromaticity", "Helix content", "Mass fit"]


def _normalize(value, lo, hi, invert=False):
    """Clamp + normalize a value to 0-1 for radar chart plotting."""
    if hi == lo:
        return 0.5
    frac = (value - lo) / (hi - lo)
    frac = max(0.0, min(1.0, frac))
    return 1 - frac if invert else frac


def compute_properties(sequence: str) -> dict:
    """
    Returns real physicochemical properties for a peptide sequence,
    computed the same way Person A's filter script and the ML
    pre-screening step do (see filter_peptides.py / data.py's
    prescreened_peptides.csv generation).

    Returns:
        {
          "raw":   {length, molecular_weight, net_charge, gravy,
                    instability, isoelectric_point, aromaticity,
                    helix_fraction, turn_fraction, sheet_fraction,
                    pct_hydrophobic, pct_positive, pct_negative, pct_polar},
          "radar": {Charge, Hydrophobicity, Stability, Aromaticity,
                    "Helix content", "Mass fit"}   # each 0-1
        }
    """
    seq = sequence.strip().upper()
    pa = ProteinAnalysis(seq)
    aa = pa.amino_acids_percent
    helix, turn, sheet = pa.secondary_structure_fraction()

    raw = {
        "length":            len(seq),
        "molecular_weight":  pa.molecular_weight(),
        "net_charge":        pa.charge_at_pH(7.0),
        "gravy":             pa.gravy(),
        "instability":       pa.instability_index(),
        "isoelectric_point": pa.isoelectric_point(),
        "aromaticity":       pa.aromaticity(),
        "helix_fraction":    helix,
        "turn_fraction":     turn,
        "sheet_fraction":    sheet,
        "pct_hydrophobic":   sum(aa.get(a, 0) for a in "AILMFWYV") * 100,
        "pct_positive":      sum(aa.get(a, 0) for a in "KRH") * 100,
        "pct_negative":      sum(aa.get(a, 0) for a in "DE") * 100,
        "pct_polar":         sum(aa.get(a, 0) for a in "STNQ") * 100,
    }

    radar = {
        "Charge":         _normalize(raw["net_charge"], *RANGES["net_charge"]),
        "Hydrophobicity": _normalize(raw["gravy"], *RANGES["gravy"]),
        "Stability":      _normalize(raw["instability"], *RANGES["instability"], invert=True),
        "Aromaticity":    _normalize(raw["aromaticity"], *RANGES["aromaticity"]),
        "Helix content":  _normalize(raw["helix_fraction"], *RANGES["helix_fraction"]),
        "Mass fit":       _normalize(raw["molecular_weight"], *RANGES["molecular_weight"]),
    }

    return {"raw": raw, "radar": radar}
