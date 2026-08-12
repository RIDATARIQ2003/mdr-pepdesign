# Save as: prepare_for_personA.py
# Run this once — produces both files for Person A

from dashboard.input_layer import resolve_structure, detect_pocket
import json, os

os.makedirs("data", exist_ok=True)

# 1 — Fetch and clean EmrE
print("="*50)
print("Fetching and cleaning EmrE (3B5D)...")
pdb_str = resolve_structure("3B5D")
with open("data/clean_protein.pdb", "w") as f:
    f.write(pdb_str)
print("✅ clean_protein.pdb saved")

# 2 — Detect pocket using E14 (known binding residue)
print("\nDetecting binding pocket...")
coords = detect_pocket(
    "data/clean_protein.pdb",
    known_residue=14,
    known_chains=['A', 'B']
)

if coords:
    with open("data/pocket_coords.txt", "w") as f:
        json.dump(coords, f, indent=2)
    print(f"✅ pocket_coords.txt saved")
    print(f"\n{'='*50}")
    print(f"FILES READY FOR PERSON A:")
    print(f"  data/clean_protein.pdb")
    print(f"  data/pocket_coords.txt")
    print(f"  Pocket: X={coords['cx']}, Y={coords['cy']}, Z={coords['cz']}")
    print(f"  Method: {coords['method']}")
    print(f"{'='*50}")
else:
    print("❌ Could not detect pocket — check PDB file")