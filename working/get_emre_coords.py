# Save as: get_emre_coords.py
# Run in same folder as clean_protein.pdb
# Or adjust path below

import json, os

def get_emre_pocket(pdb_file):
    coords = []
    with open(pdb_file) as f:
        for line in f:
            if not line.startswith('ATOM'): continue
            res_num = int(line[22:26].strip())
            chain   = line[21].strip()
            if res_num == 14 and chain in ['A', 'B']:
                coords.append((
                    float(line[30:38]),
                    float(line[38:46]),
                    float(line[46:54])
                ))

    if not coords:
        print("❌ E14 not found — check your PDB file")
        return None

    cx = sum(c[0] for c in coords) / len(coords)
    cy = sum(c[1] for c in coords) / len(coords)
    cz = sum(c[2] for c in coords) / len(coords)

    result = {
        "cx"    : round(cx, 3),
        "cy"    : round(cy, 3),
        "cz"    : round(cz, 3),
        "volume": 300.0,
        "method": "known_residue_E14"
    }
    return result

# Run it
coords = get_emre_pocket("data/clean_protein.pdb")

if coords:
    os.makedirs("data", exist_ok=True)
    with open("data/pocket_coords.txt", "w") as f:
        json.dump(coords, f, indent=2)
    print(f"✅ pocket_coords.txt saved")
    print(f"   X: {coords['cx']}")
    print(f"   Y: {coords['cy']}")
    print(f"   Z: {coords['cz']}")
    print(f"   Method: {coords['method']}")